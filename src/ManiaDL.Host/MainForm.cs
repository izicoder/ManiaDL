using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using ManiaDL.Core.Config;
using ManiaDL.Core.Engine;
using ManiaDL.Core.Logging;
using ManiaDL.Core.Util;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace ManiaDL.Host;

/// <summary>
/// Minimal WinForms shell around one WebView2 control. It owns no business logic:
/// it serves the embedded frontend, forwards bridge messages and pumps engine events.
/// </summary>
public sealed class MainForm : Form
{
    private static readonly JsonSerializerOptions BridgeJson = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false,
    };

    private static readonly Regex[] AllowedLinks =
    {
        new(@"^https://osu\.ppy\.sh/beatmapsets/\d+$", RegexOptions.CultureInvariant),
        new(@"^https://osu\.ppy\.sh/home/account/edit$", RegexOptions.CultureInvariant),
    };

    private const string AppOrigin = "https://maniadl.app";

    private readonly HostOptions _options;
    private readonly AppPaths _paths;
    private readonly ConfigStore _store;
    private readonly IEngine _engine;
    private readonly WebView2 _webView = new();
    private readonly CancellationTokenSource _pumpStop = new();

    private RawConfig _config;
    private bool _allowClose;
    private bool _closeRequested;

    public MainForm(HostOptions options, AppPaths paths, ConfigStore store, IEngine engine)
    {
        _options = options;
        _paths = paths;
        _store = store;
        _engine = engine;

        var (saved, changed) = store.LoadAndMigrate();
        if (changed && (saved.ClientId.Length > 0 || saved.ClientSecret.Length > 0))
        {
            store.Save(saved);
        }

        _config = saved;
        if (_config.Out.Length == 0)
        {
            _config.Out = paths.DefaultOut;
        }

        Text = "ManiaDL";
        Width = 1200;
        Height = 820;
        MinimumSize = new Size(1000, 680);
        BackColor = ColorTranslator.FromHtml("#111318");
        StartPosition = FormStartPosition.CenterScreen;

        _webView.Dock = DockStyle.Fill;
        _webView.DefaultBackgroundColor = ColorTranslator.FromHtml("#111318");
        Controls.Add(_webView);

        Load += async (_, _) => await InitialiseWebViewAsync();
        FormClosing += OnFormClosingHandler;
    }

    private async Task InitialiseWebViewAsync()
    {
        try
        {
            var userData = string.IsNullOrWhiteSpace(_options.DataDir)
                ? Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "ManiaDL", "WebView2")
                : Path.Combine(_options.DataDir, "webview2");
            Directory.CreateDirectory(userData);

            var environmentOptions = new CoreWebView2EnvironmentOptions();
            if (_options.DebugPort is not null)
            {
                environmentOptions.AdditionalBrowserArguments =
                    $"--remote-debugging-port={_options.DebugPort.Value}";
            }

            var environment = await CoreWebView2Environment.CreateAsync(
                null, userData, environmentOptions);
            await _webView.EnsureCoreWebView2Async(environment);
            var core = _webView.CoreWebView2;

            core.Settings.AreDefaultContextMenusEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = false;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreDevToolsEnabled = _options.DebugPort is not null;

            core.AddWebResourceRequestedFilter($"{AppOrigin}/*", CoreWebView2WebResourceContext.All);
            core.WebResourceRequested += OnWebResourceRequested;
            core.WebMessageReceived += OnWebMessageReceived;
            core.NavigationStarting += OnNavigationStarting;
            core.NewWindowRequested += (_, args) => args.Handled = true;

            if (!string.IsNullOrWhiteSpace(_options.DevUrl))
            {
                core.Navigate(_options.DevUrl);
            }
            else
            {
                core.Navigate($"{AppOrigin}/index.html");
            }

            _ = PumpEngineEventsAsync();
            ApplyDarkTitleBar();
        }
        catch (WebView2RuntimeNotFoundException)
        {
            MessageBox.Show(
                this,
                "ManiaDL needs the Microsoft Edge WebView2 Runtime.\n\n" +
                "Install it from https://go.microsoft.com/fwlink/p/?LinkId=2124703 and start ManiaDL again.",
                "ManiaDL",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            Close();
        }
    }

    private void OnWebResourceRequested(object? sender, CoreWebView2WebResourceRequestedEventArgs args)
    {
        var core = _webView.CoreWebView2;
        var uri = new Uri(args.Request.Uri);
        var path = uri.AbsolutePath.TrimStart('/');
        if (path.Length == 0)
        {
            path = "index.html";
        }

        var assembly = typeof(MainForm).Assembly;
        var stream = assembly.GetManifestResourceStream($"ui/{path}");
        if (stream is null && !Path.HasExtension(path))
        {
            path = "index.html";
            stream = assembly.GetManifestResourceStream("ui/index.html");
        }

        if (stream is null)
        {
            args.Response = core.Environment.CreateWebResourceResponse(
                null, 404, "Not Found", "Content-Type: text/plain");
            return;
        }

        args.Response = core.Environment.CreateWebResourceResponse(
            stream, 200, "OK", $"Content-Type: {MimeType(path)}");
    }

    private static string MimeType(string path) => Path.GetExtension(path).ToLowerInvariant() switch
    {
        ".html" => "text/html; charset=utf-8",
        ".js" => "text/javascript; charset=utf-8",
        ".mjs" => "text/javascript; charset=utf-8",
        ".css" => "text/css; charset=utf-8",
        ".json" => "application/json",
        ".svg" => "image/svg+xml",
        ".png" => "image/png",
        ".jpg" or ".jpeg" => "image/jpeg",
        ".woff2" => "font/woff2",
        ".woff" => "font/woff",
        ".ico" => "image/x-icon",
        _ => "application/octet-stream",
    };

    private void OnNavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs args)
    {
        var allowed = args.Uri.StartsWith(AppOrigin, StringComparison.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(_options.DevUrl))
        {
            allowed |= args.Uri.StartsWith(_options.DevUrl, StringComparison.OrdinalIgnoreCase);
        }

        if (!allowed)
        {
            args.Cancel = true;
        }
    }

    private async void OnWebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        try
        {
            if (!IsAllowedSource(args.Source))
            {
                return;
            }

            using var document = JsonDocument.Parse(args.WebMessageAsJson);
            var root = document.RootElement;
            if (!root.TryGetProperty("type", out var typeElement))
            {
                return;
            }

            switch (typeElement.GetString())
            {
                case "ready":
                    SendInit();
                    break;
                case "saveSettings":
                    MergeSettings(root);
                    _store.Save(_config);
                    break;
                case "resetSettings":
                    ResetAdvanced();
                    SendSettings();
                    break;
                case "start":
                    MergeSettings(root);
                    await StartRunAsync();
                    break;
                case "stop":
                    _engine.Stop();
                    break;
                case "openUrl":
                    OpenUrl(root);
                    break;
                case "copyText":
                    CopyText(root);
                    break;
                case "pickFolder":
                    PickFolder();
                    break;
                case "closeConfirmed":
                    ConfirmClose();
                    break;
            }
        }
        catch (JsonException)
        {
            // Malformed bridge message: ignore rather than crash the shell.
        }
    }

    private bool IsAllowedSource(string source)
    {
        if (string.IsNullOrEmpty(source))
        {
            return false;
        }

        if (source.StartsWith(AppOrigin, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return !string.IsNullOrWhiteSpace(_options.DevUrl) &&
               source.StartsWith(_options.DevUrl, StringComparison.OrdinalIgnoreCase);
    }

    private async Task StartRunAsync()
    {
        var outcome = await _engine.StartAsync(_config);
        if (!outcome.Started)
        {
            Post(new { type = "error", message = outcome.Error, field = outcome.Field });
        }
    }

    private void MergeSettings(JsonElement root)
    {
        if (!root.TryGetProperty("settings", out var settings) ||
            settings.ValueKind != JsonValueKind.Object)
        {
            return;
        }

        var incoming = JsonSerializer.Deserialize<RawConfig>(
            settings.GetRawText(), ConfigStore.JsonOptions);
        if (incoming is not null)
        {
            _config.CopyFrom(incoming);
            _config.PresentKeys = incoming.PresentKeys;
        }
    }

    /// <summary>Python's Reset button: clears advanced values, keeps the toggle as-is.</summary>
    private void ResetAdvanced()
    {
        _config.Query = "";
        _config.Title = "";
        _config.Artist = "";
        _config.Creator = "";
        _config.Source = "";
        _config.Exclude = "";
        _config.Genre = "";
        _config.Language = "";
        _config.BpmRange = "";
        _config.LengthRange = "";
        _config.NotesRange = "";
        _config.MinPlays = "0";
        _config.RankedRange = "";
        _config.IncludeNsfw = false;
    }

    private void SendInit()
    {
        var settings = JsonSerializer.SerializeToElement(SettingsForUi(), ConfigStore.JsonOptions);
        Post(new
        {
            type = "init",
            protocolVersion = 1,
            appVersion = typeof(MainForm).Assembly.GetName().Version?.ToString(3) ?? "3.0.0",
            settings,
            envOverride = HasEnvCredentials(),
            failed = Array.Empty<object>(),
        });
    }

    private void SendSettings()
    {
        var settings = JsonSerializer.SerializeToElement(SettingsForUi(), ConfigStore.JsonOptions);
        Post(new { type = "settings", settings });
    }

    private RawConfig SettingsForUi()
    {
        var config = _config.Clone();
        var envId = Environment.GetEnvironmentVariable("OSU_CLIENT_ID");
        var envSecret = Environment.GetEnvironmentVariable("OSU_CLIENT_SECRET");
        if (!string.IsNullOrEmpty(envId))
        {
            config.ClientId = envId;
        }

        if (!string.IsNullOrEmpty(envSecret))
        {
            config.ClientSecret = envSecret;
        }

        return config;
    }

    private static bool HasEnvCredentials() =>
        !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("OSU_CLIENT_ID")) ||
        !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("OSU_CLIENT_SECRET"));

    private void OpenUrl(JsonElement root)
    {
        if (!root.TryGetProperty("url", out var urlElement))
        {
            return;
        }

        var url = urlElement.GetString() ?? "";
        if (!AllowedLinks.Any(link => link.IsMatch(url)))
        {
            return;
        }

        Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
    }

    private void CopyText(JsonElement root)
    {
        var text = root.TryGetProperty("text", out var textElement)
            ? textElement.GetString() ?? ""
            : "";

        if (_options.DebugPort is not null)
        {
            // Test hook: lets the e2e harness assert clipboard contents without
            // touching the system clipboard.
            File.WriteAllText(Path.Combine(_paths.BaseDirectory, "clipboard.txt"), text);
        }

        try
        {
            Clipboard.SetText(text);
        }
        catch (System.Runtime.InteropServices.ExternalException)
        {
            // Clipboard disabled in this session; the text was still handed over.
        }
    }

    private void PickFolder()
    {
        using var dialog = new FolderBrowserDialog
        {
            SelectedPath = Directory.Exists(_config.Out) ? _config.Out : _paths.BaseDirectory,
        };
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            Post(new { type = "folderPicked", path = dialog.SelectedPath });
        }
    }

    private async Task PumpEngineEventsAsync()
    {
        try
        {
            await foreach (var engineEvent in _engine.Events.ReadAllAsync(_pumpStop.Token))
            {
                if (IsDisposed)
                {
                    return;
                }

                BeginInvoke(() => Forward(engineEvent));
            }
        }
        catch (OperationCanceledException)
        {
            // Window closed.
        }
        catch (InvalidOperationException)
        {
            // Handle destroyed while an event was pending.
        }
    }

    private void Forward(EngineEvent engineEvent)
    {
        if (IsDisposed || _webView.CoreWebView2 is null)
        {
            return;
        }

        switch (engineEvent)
        {
            case StateChangedEvent state:
                Post(new { type = "state", state = state.State, detail = state.Detail });
                break;
            case LogBatchEvent batch:
                Post(new
                {
                    type = "log",
                    entries = batch.Entries.Select(entry => new
                    {
                        t = entry.Time.ToString("o"),
                        level = entry.LevelName,
                        msg = entry.Message,
                    }),
                });
                break;
            case ProgressEvent progress:
                Post(new { type = "progress", value = progress.Value });
                break;
            case DoneEvent done:
                Post(new { type = "done", result = done.Result });
                break;
            case EngineErrorEvent error:
                Post(new { type = "error", message = error.Message, field = error.Field });
                break;
        }
    }

    private void Post(object payload)
    {
        var core = _webView.CoreWebView2;
        if (core is null)
        {
            return;
        }

        core.PostWebMessageAsJson(JsonSerializer.Serialize(payload, BridgeJson));
    }

    private void OnFormClosingHandler(object? sender, FormClosingEventArgs args)
    {
        if (_allowClose || _engine.State == EngineState.Idle)
        {
            _pumpStop.Cancel();
            return;
        }

        args.Cancel = true;
        if (!_closeRequested)
        {
            _closeRequested = true;
            Post(new { type = "closeRequested" });
        }
    }

    private void ConfirmClose()
    {
        _engine.Stop();
        _allowClose = true;

        if (_engine.State == EngineState.Idle)
        {
            Close();
            return;
        }

        var timer = new System.Windows.Forms.Timer { Interval = 100 };
        timer.Tick += (_, _) =>
        {
            if (_engine.State != EngineState.Idle)
            {
                return;
            }

            timer.Stop();
            timer.Dispose();
            Close();
        };
        timer.Start();
    }

    private void ApplyDarkTitleBar()
    {
        try
        {
            var enabled = 1;
            foreach (var attribute in new[] { 20, 19 })
            {
                if (DwmSetWindowAttribute(Handle, attribute, ref enabled, sizeof(int)) == 0)
                {
                    break;
                }
            }
        }
        catch (DllNotFoundException)
        {
            // Non-Windows or older DWM: keep the default title bar.
        }
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(
        IntPtr hwnd, int attribute, ref int value, int size);
}
