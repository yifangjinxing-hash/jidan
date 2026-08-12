using System;
using System.IO;
using System.Reflection;
using System.Windows;

namespace JidanOS
{
    public static class Program
    {
        [STAThread]
        public static int Main(string[] args)
        {
            if (args.Length > 0 && String.Equals(args[0], "--self-test", StringComparison.OrdinalIgnoreCase))
                return 27;

            if (args.Length > 0 && String.Equals(args[0], "--test", StringComparison.OrdinalIgnoreCase))
            {
                string output = args.Length > 1 ? args[1] : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "test-results.txt");
                return TestHarness.Run(output) ? 0 : 1;
            }

            if (args.Length > 2 && String.Equals(args[0], "--inspect", StringComparison.OrdinalIgnoreCase))
            {
                try
                {
                    PackageInspector inspector = new PackageInspector();
                    ArtifactInfo artifact = inspector.Inspect(args[1], false);
                    File.WriteAllText(args[2], TestHarness.FormatArtifact(artifact));
                    return 0;
                }
                catch (Exception error)
                {
                    File.WriteAllText(args[2], "ERROR\r\n" + error);
                    return 2;
                }
            }

            try
            {
                Application application = new Application();
                application.ShutdownMode = ShutdownMode.OnMainWindowClose;
                MainWindowController controller = new MainWindowController();
                application.MainWindow = controller.Window;
                application.Run(controller.Window);
                return 0;
            }
            catch (Exception error)
            {
                MessageBox.Show(error.ToString(), "JidanOS could not start", MessageBoxButton.OK, MessageBoxImage.Error);
                return 1;
            }
        }
    }
}
