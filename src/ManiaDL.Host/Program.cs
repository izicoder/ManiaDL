using ManiaDL.Core.Config;
using ManiaDL.Core.Constants;
using ManiaDL.Core.Engine;
using ManiaDL.Core.Run;
using ManiaDL.Core.Util;

namespace ManiaDL.Host;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        var options = HostOptions.Parse(args);
        var baseDirectory = string.IsNullOrWhiteSpace(options.DataDir)
            ? AppContext.BaseDirectory
            : options.DataDir;
        Directory.CreateDirectory(baseDirectory);

        var paths = new AppPaths(baseDirectory);
        var store = new ConfigStore(paths);

        IEngine engine = options.FakeScenario is null
            ? new Engine(
                paths,
                store,
                orchestratorFactory: ctx => new DownloadOrchestrator(
                    ctx, apiBase: options.ApiBase ?? ApiEndpoints.Api))
            : new FakeEngine(paths, store, options.FakeScenario);

        Application.Run(new MainForm(options, paths, store, engine));
    }
}
