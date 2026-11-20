using System.Text;

namespace ManiaDL.Core.Util;

/// <summary>Atomic UTF-8 writes: write <c>&lt;name&gt;.tmp</c>, then replace.</summary>
public static class AtomicFile
{
    public static void WriteText(string path, string text)
    {
        var tmp = path + ".tmp";
        try
        {
            File.WriteAllText(tmp, text, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
            File.Move(tmp, path, overwrite: true);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            try
            {
                File.Delete(tmp);
            }
            catch (Exception cleanup) when (cleanup is IOException or UnauthorizedAccessException)
            {
                // Nothing useful to do; the original exception is what matters.
            }

            throw;
        }
    }
}
