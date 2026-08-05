using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Shapes;
using System.Xml;
using Microsoft.Win32;

namespace JidanOS
{
    public sealed class MainWindowController
    {
        public Window Window { get; private set; }

        private readonly PackageInspector inspector;
        private readonly List<ArtifactInfo> artifacts;
        private List<SystemProfile> systems;
        private SystemProfile selectedSystem;
        private ArtifactInfo selectedArtifact;

        private StackPanel systemList;
        private StackPanel packageList;
        private StackPanel metadataPanel;
        private StackPanel tracePanel;
        private TextBlock packageFilterLabel;
        private TextBlock packageCountLabel;
        private TextBlock activeSystemName;
        private TextBlock activeSystemEngine;
        private TextBlock activeSystemStatus;
        private TextBlock sessionSystemLabel;
        private Ellipse sessionLed;
        private TextBlock sessionStateLabel;
        private Border sessionGlyphBorder;
        private TextBlock sessionGlyph;
        private TextBlock sessionTitle;
        private TextBlock sessionMessage;
        private TextBox sessionOutput;
        private TextBlock artifactName;
        private TextBlock artifactIdentity;
        private TextBlock compatibilityStatus;
        private TextBlock compatibilitySummary;
        private TextBlock artifactKindLabel;
        private TextBlock statusBarText;
        private Button runPackageButton;
        private Button bootSystemButton;
        private Button settingsActionButton;
        private Button paymentActionButton;
        private Button voiceActionButton;

        public MainWindowController()
        {
            inspector = new PackageInspector();
            artifacts = new List<ArtifactInfo>();
            LoadWindow();
            BindControls();
            BindEvents();
            LoadBuiltInPackages();
            RefreshSystems("jidan");
            if (selectedSystem != null) BootSelectedSystem();
        }

        private void LoadWindow()
        {
            Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("JidanOS.MainWindow.xaml");
            if (stream == null) throw new InvalidOperationException("Embedded native window resource is missing.");
            using (stream)
            using (XmlReader reader = XmlReader.Create(stream))
                Window = (Window)XamlReader.Load(reader);
        }

        private void BindControls()
        {
            systemList = Find<StackPanel>("SystemList");
            packageList = Find<StackPanel>("PackageList");
            metadataPanel = Find<StackPanel>("MetadataPanel");
            tracePanel = Find<StackPanel>("TracePanel");
            packageFilterLabel = Find<TextBlock>("PackageFilterLabel");
            packageCountLabel = Find<TextBlock>("PackageCountLabel");
            activeSystemName = Find<TextBlock>("ActiveSystemName");
            activeSystemEngine = Find<TextBlock>("ActiveSystemEngine");
            activeSystemStatus = Find<TextBlock>("ActiveSystemStatus");
            sessionSystemLabel = Find<TextBlock>("SessionSystemLabel");
            sessionLed = Find<Ellipse>("SessionLed");
            sessionStateLabel = Find<TextBlock>("SessionStateLabel");
            sessionGlyphBorder = Find<Border>("SessionGlyphBorder");
            sessionGlyph = Find<TextBlock>("SessionGlyph");
            sessionTitle = Find<TextBlock>("SessionTitle");
            sessionMessage = Find<TextBlock>("SessionMessage");
            sessionOutput = Find<TextBox>("SessionOutput");
            artifactName = Find<TextBlock>("ArtifactName");
            artifactIdentity = Find<TextBlock>("ArtifactIdentity");
            compatibilityStatus = Find<TextBlock>("CompatibilityStatus");
            compatibilitySummary = Find<TextBlock>("CompatibilitySummary");
            artifactKindLabel = Find<TextBlock>("ArtifactKindLabel");
            statusBarText = Find<TextBlock>("StatusBarText");
            runPackageButton = Find<Button>("RunPackageButton");
            bootSystemButton = Find<Button>("BootSystemButton");
            settingsActionButton = Find<Button>("SettingsActionButton");
            paymentActionButton = Find<Button>("PaymentActionButton");
            voiceActionButton = Find<Button>("VoiceActionButton");
        }

        private void BindEvents()
        {
            Find<Button>("ImportButton").Click += delegate { OpenPackageDialog(); };
            Find<Button>("RefreshButton").Click += delegate { RefreshAll(); };
            runPackageButton.Click += delegate { RunSelectedPackage("boot"); };
            bootSystemButton.Click += delegate { BootSelectedSystem(); };
            settingsActionButton.Click += delegate { RunSelectedPackage("settings"); };
            paymentActionButton.Click += delegate { RunSelectedPackage("payment"); };
            voiceActionButton.Click += delegate { RunSelectedPackage("voice"); };
            Window.DragOver += OnDragOver;
            Window.Drop += OnDrop;
            Window.PreviewKeyDown += OnPreviewKeyDown;
        }

        private void LoadBuiltInPackages()
        {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            AddPackage(Assembly.GetExecutingAssembly().Location, true, false);
            AddPackage(System.IO.Path.Combine(root, "samples", "JidanDemo.apk"), true, false);
            AddPackage(System.IO.Path.Combine(root, "samples", "JidanDemo.ipa"), true, false);
        }

        private void AddPackage(string path, bool builtIn, bool select)
        {
            if (!File.Exists(path)) return;
            string fullPath = System.IO.Path.GetFullPath(path);
            ArtifactInfo existing = artifacts.FirstOrDefault(item => String.Equals(item.Path, fullPath, StringComparison.OrdinalIgnoreCase));
            if (existing != null)
            {
                if (select) SelectArtifact(existing);
                return;
            }
            try
            {
                ArtifactInfo artifact = inspector.Inspect(fullPath, builtIn);
                artifacts.Add(artifact);
                statusBarText.Text = "已识别 " + artifact.KindLabel + " · " + artifact.Name + " · " + artifact.Sha256.Substring(0, 12);
                if (selectedSystem != null) RenderPackages();
                if (select) SelectArtifact(artifact);
            }
            catch (Exception error)
            {
                statusBarText.Text = "导入失败 · " + error.Message;
                if (select) MessageBox.Show(Window, error.Message, "无法导入成品包", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
        }

        private void RefreshAll()
        {
            string systemId = selectedSystem == null ? "jidan" : selectedSystem.Id;
            List<ArtifactInfo> refreshed = new List<ArtifactInfo>();
            string selectedPath = selectedArtifact == null ? null : selectedArtifact.Path;
            for (int index = 0; index < artifacts.Count; index++)
            {
                try { refreshed.Add(inspector.Inspect(artifacts[index].Path, artifacts[index].BuiltIn)); }
                catch { }
            }
            artifacts.Clear();
            artifacts.AddRange(refreshed);
            RefreshSystems(systemId);
            if (selectedPath != null)
            {
                ArtifactInfo match = artifacts.FirstOrDefault(item => String.Equals(item.Path, selectedPath, StringComparison.OrdinalIgnoreCase));
                if (match != null) SelectArtifact(match);
            }
            statusBarText.Text = "运行引擎和成品包状态已刷新";
        }

        private void RefreshSystems(string selectedId)
        {
            systems = SystemCatalog.Detect();
            selectedSystem = systems.FirstOrDefault(profile => profile.Id == selectedId) ?? systems[0];
            RenderSystems();
            RenderPackages();
            UpdateSystemHeader();
        }

        private void RenderSystems()
        {
            systemList.Children.Clear();
            for (int index = 0; index < systems.Count; index++)
            {
                SystemProfile profile = systems[index];
                Button button = new Button();
                button.Style = (Style)Window.Resources["FlatButton"];
                button.Tag = profile;
                button.Margin = new Thickness(0, 0, 0, 8);
                button.Background = profile == selectedSystem ? Brush("#182019") : Brushes.Transparent;
                button.BorderBrush = profile == selectedSystem ? Brush(profile.Accent) : Brush("#273029");
                button.Click += OnSystemClick;

                Grid grid = new Grid();
                grid.Margin = new Thickness(11, 11, 9, 11);
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(5) });
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                Border accent = new Border();
                accent.Background = Brush(profile.Accent);
                accent.CornerRadius = new CornerRadius(2);
                grid.Children.Add(accent);
                StackPanel content = new StackPanel();
                content.Margin = new Thickness(12, 0, 0, 0);
                Grid.SetColumn(content, 1);
                TextBlock name = new TextBlock { Text = profile.Name, FontSize = 15, FontWeight = FontWeights.SemiBold, Foreground = Brush("#F2F5F0") };
                TextBlock subtitle = new TextBlock { Text = profile.Subtitle, Foreground = Brush("#7E8981"), FontSize = 11, Margin = new Thickness(0, 3, 0, 0) };
                TextBlock status = new TextBlock { Text = profile.Status, Foreground = ToneBrush(profile.Tone, profile.Accent), FontSize = 10, Margin = new Thickness(0, 5, 0, 0), FontFamily = new FontFamily("Cascadia Mono, Consolas") };
                content.Children.Add(name);
                content.Children.Add(subtitle);
                content.Children.Add(status);
                grid.Children.Add(content);
                button.Content = grid;
                systemList.Children.Add(button);
            }
        }

        private void OnSystemClick(object sender, RoutedEventArgs args)
        {
            Button button = sender as Button;
            SystemProfile profile = button == null ? null : button.Tag as SystemProfile;
            if (profile == null) return;
            selectedSystem = profile;
            selectedArtifact = null;
            RenderSystems();
            UpdateSystemHeader();
            ClearArtifact();
            BootSelectedSystem();
            RenderPackages();
        }

        private void UpdateSystemHeader()
        {
            if (selectedSystem == null) return;
            SolidColorBrush accent = Brush(selectedSystem.Accent);
            activeSystemName.Text = selectedSystem.Name;
            activeSystemEngine.Text = selectedSystem.Engine;
            activeSystemStatus.Text = selectedSystem.Status;
            activeSystemStatus.Foreground = ToneBrush(selectedSystem.Tone, selectedSystem.Accent);
            sessionSystemLabel.Text = selectedSystem.Name.ToUpperInvariant() + " SYSTEM SESSION";
            sessionGlyph.Text = SystemGlyph(selectedSystem.Id);
            sessionGlyph.Foreground = accent;
            sessionGlyphBorder.BorderBrush = accent;
            runPackageButton.Background = accent;
            runPackageButton.BorderBrush = accent;
            bootSystemButton.Content = selectedSystem.CanBoot ? "启动所选系统" : "查看缺失引擎";
        }

        private void RenderPackages()
        {
            packageList.Children.Clear();
            List<ArtifactInfo> visible = VisibleArtifacts();
            packageCountLabel.Text = visible.Count.ToString();
            packageFilterLabel.Text = selectedSystem == null || selectedSystem.Id == "jidan" ? "Jidan · 全部平台" : selectedSystem.Name + " 成品包";
            for (int index = 0; index < visible.Count; index++)
            {
                ArtifactInfo artifact = visible[index];
                Button button = new Button();
                button.Style = (Style)Window.Resources["FlatButton"];
                button.Tag = artifact;
                button.Margin = new Thickness(0, 0, 0, 8);
                button.Background = artifact == selectedArtifact ? Brush("#182019") : Brush("#0E1310");
                button.BorderBrush = artifact == selectedArtifact ? KindBrush(artifact.Kind) : Brush("#273029");
                button.Click += OnPackageClick;

                Grid grid = new Grid { Margin = new Thickness(10) };
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(45) });
                grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                Border icon = new Border { Width = 39, Height = 39, Background = KindBrush(artifact.Kind), CornerRadius = new CornerRadius(5), VerticalAlignment = VerticalAlignment.Top };
                icon.Child = new TextBlock { Text = artifact.KindLabel, Foreground = Brush("#081008"), FontWeight = FontWeights.Bold, FontSize = 10, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, FontFamily = new FontFamily("Cascadia Mono, Consolas") };
                grid.Children.Add(icon);
                StackPanel content = new StackPanel { Margin = new Thickness(9, 0, 0, 0) };
                Grid.SetColumn(content, 1);
                content.Children.Add(new TextBlock { Text = artifact.Name, Foreground = Brush("#F2F5F0"), FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis });
                content.Children.Add(new TextBlock { Text = artifact.KindLabel + " · " + artifact.Architecture, Foreground = Brush("#78837A"), FontSize = 10, Margin = new Thickness(0, 3, 0, 0), FontFamily = new FontFamily("Cascadia Mono, Consolas") });
                content.Children.Add(new TextBlock { Text = artifact.Status, Foreground = ToneBrush(artifact.StatusTone, "#B9FF57"), FontSize = 10, Margin = new Thickness(0, 4, 0, 0) });
                grid.Children.Add(content);
                button.Content = grid;
                packageList.Children.Add(button);
            }

            if (visible.Count == 0)
            {
                Border empty = new Border { BorderBrush = Brush("#273029"), BorderThickness = new Thickness(1), Padding = new Thickness(14), CornerRadius = new CornerRadius(4) };
                empty.Child = new TextBlock { Text = selectedSystem != null && selectedSystem.Id == "windowsphone" ? "Windows Phone 引擎槽已建立；尚无可运行包。" : "当前系统槽没有成品包。", Foreground = Brush("#7E8981"), TextWrapping = TextWrapping.Wrap };
                packageList.Children.Add(empty);
            }

            if (selectedArtifact == null && visible.Count > 0) SelectArtifact(visible[0]);
        }

        private List<ArtifactInfo> VisibleArtifacts()
        {
            if (selectedSystem == null || selectedSystem.Id == "jidan") return new List<ArtifactInfo>(artifacts);
            if (selectedSystem.Id == "windowsphone") return new List<ArtifactInfo>();
            return artifacts.Where(item => item.Kind == selectedSystem.FilterKind).ToList();
        }

        private void OnPackageClick(object sender, RoutedEventArgs args)
        {
            Button button = sender as Button;
            ArtifactInfo artifact = button == null ? null : button.Tag as ArtifactInfo;
            if (artifact != null) SelectArtifact(artifact);
        }

        private void SelectArtifact(ArtifactInfo artifact)
        {
            selectedArtifact = artifact;
            RenderPackages();
            artifactName.Text = artifact.Name;
            artifactIdentity.Text = artifact.Identity;
            compatibilityStatus.Text = artifact.Status;
            compatibilityStatus.Foreground = ToneBrush(artifact.StatusTone, "#B9FF57");
            compatibilitySummary.Text = artifact.Summary;
            artifactKindLabel.Text = artifact.KindLabel + " · " + artifact.Architecture;
            artifactKindLabel.Foreground = KindBrush(artifact.Kind);
            metadataPanel.Children.Clear();
            for (int index = 0; index < artifact.Metadata.Count; index++) AddMetadataRow(artifact.Metadata[index]);
            sessionTitle.Text = artifact.Name;
            sessionMessage.Text = artifact.Summary;
            sessionOutput.Text = "Route " + artifact.Route.ToString().ToUpperInvariant() + Environment.NewLine + "SHA-256 " + artifact.Sha256 + Environment.NewLine + "尚未执行。";
            sessionStateLabel.Text = "READY TO ROUTE";
            sessionStateLabel.Foreground = ToneBrush(artifact.StatusTone, "#B9FF57");
            sessionLed.Fill = ToneBrush(artifact.StatusTone, "#B9FF57");
            tracePanel.Children.Clear();
            AddTraceRow(new ExecutionTrace { Lane = "·", Address = artifact.KindLabel, Instruction = "inspect", Effect = "package identified; not executed" });
            runPackageButton.Content = artifact.CanRun ? "运行 " + artifact.KindLabel : (artifact.Kind == ArtifactKind.AndroidApk ? "配置 Android 引擎" : "查看缺失能力");
            bool commands = artifact.Kind == ArtifactKind.AppleIpa && artifact.CanRun && artifact.Tags.ContainsKey("commandOffset") && artifact.Tags["commandOffset"] != "-1";
            settingsActionButton.Visibility = commands ? Visibility.Visible : Visibility.Collapsed;
            paymentActionButton.Visibility = commands ? Visibility.Visible : Visibility.Collapsed;
            voiceActionButton.Visibility = commands ? Visibility.Visible : Visibility.Collapsed;
            statusBarText.Text = "已选择 " + artifact.Name + " · " + artifact.Route;
        }

        private void ClearArtifact()
        {
            artifactName.Text = "未选择";
            artifactIdentity.Text = "—";
            compatibilityStatus.Text = "等待选择";
            compatibilitySummary.Text = "选择当前系统槽中的成品包。";
            artifactKindLabel.Text = "—";
            metadataPanel.Children.Clear();
            settingsActionButton.Visibility = Visibility.Collapsed;
            paymentActionButton.Visibility = Visibility.Collapsed;
            voiceActionButton.Visibility = Visibility.Collapsed;
        }

        private void BootSelectedSystem()
        {
            if (selectedSystem == null) return;
            SolidColorBrush accent = Brush(selectedSystem.Accent);
            sessionLed.Fill = selectedSystem.CanBoot ? accent : Brush("#FF6675");
            sessionStateLabel.Foreground = selectedSystem.CanBoot ? accent : Brush("#FF6675");
            if (selectedSystem.CanBoot)
            {
                sessionStateLabel.Text = "ENGINE READY";
                sessionTitle.Text = selectedSystem.Name + " 系统槽已就绪";
                sessionMessage.Text = "运行引擎：" + selectedSystem.Engine + "。选择成品包即可建立真实执行会话。";
                sessionOutput.Text = "System " + selectedSystem.Name + Environment.NewLine + "Engine " + selectedSystem.Engine + Environment.NewLine + "State READY";
                tracePanel.Children.Clear();
                AddTraceRow(new ExecutionTrace { Lane = selectedSystem.Id == "ios" ? "H" : "N", Address = "SYSTEM", Instruction = "select " + selectedSystem.Id, Effect = selectedSystem.Engine + " ready" });
            }
            else
            {
                sessionStateLabel.Text = "ENGINE MISSING";
                sessionTitle.Text = selectedSystem.Name + " 还不能启动";
                sessionMessage.Text = "系统槽已建立，但当前版本缺少 " + selectedSystem.Engine + "。没有伪造 guest 会话。";
                sessionOutput.Text = "未执行：没有匹配的系统引擎。";
                tracePanel.Children.Clear();
                AddTraceRow(new ExecutionTrace { Lane = "D", Address = "SYSTEM", Instruction = "select " + selectedSystem.Id, Effect = "backend missing" });
            }
            statusBarText.Text = selectedSystem.Name + " · " + selectedSystem.Status;
        }

        private void RunSelectedPackage(string action)
        {
            if (selectedArtifact == null)
            {
                BootSelectedSystem();
                return;
            }

            if (selectedArtifact.Kind == ArtifactKind.WindowsExe && !selectedArtifact.BuiltIn && selectedArtifact.CanRun)
            {
                string warning = "允许这个 EXE 在本机运行？\n\n" + selectedArtifact.Path + "\nSHA-256 " + selectedArtifact.Sha256 + "\n\n本版本没有为陌生 EXE 提供安全隔离；它可能读取或修改 Windows 文件。";
                MessageBoxResult choice = MessageBox.Show(Window, warning, "确认原生执行", MessageBoxButton.YesNo, MessageBoxImage.Warning, MessageBoxResult.No);
                if (choice != MessageBoxResult.Yes) return;
            }

            sessionStateLabel.Text = "STARTING";
            sessionLed.Fill = Brush("#F1C45E");
            Window.Cursor = Cursors.Wait;
            try
            {
                ExecutionResult result = inspector.Run(selectedArtifact, action);
                DisplayExecution(result);
            }
            finally
            {
                Window.Cursor = Cursors.Arrow;
            }
        }

        private void DisplayExecution(ExecutionResult result)
        {
            sessionTitle.Text = result.Title;
            sessionMessage.Text = result.Message;
            sessionOutput.Text = String.IsNullOrWhiteSpace(result.Output) ? "No output." : result.Output;
            bool policyBlock = result.Title.IndexOf("blocked", StringComparison.OrdinalIgnoreCase) >= 0;
            Brush state = result.Success ? (policyBlock ? Brush("#F1C45E") : Brush("#B9FF57")) : Brush("#FF6675");
            sessionLed.Fill = state;
            sessionStateLabel.Foreground = state;
            sessionStateLabel.Text = result.Success ? (policyBlock ? "POLICY BLOCK" : "SESSION COMPLETE") : "NOT EXECUTED";
            tracePanel.Children.Clear();
            if (result.Trace.Count == 0) AddTraceRow(new ExecutionTrace { Lane = "D", Address = "—", Instruction = "no session", Effect = "nothing executed" });
            for (int index = 0; index < result.Trace.Count; index++) AddTraceRow(result.Trace[index]);
            statusBarText.Text = result.Title + " · " + result.Trace.Count + " evidence events";
        }

        private void AddMetadataRow(MetadataItem item)
        {
            Border border = new Border { BorderBrush = Brush("#222A24"), BorderThickness = new Thickness(0, 0, 0, 1), Padding = new Thickness(0, 10, 0, 10) };
            Grid grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(102) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            TextBlock name = new TextBlock { Text = item.Name, Foreground = Brush("#69736B"), FontSize = 9, FontFamily = new FontFamily("Cascadia Mono, Consolas"), VerticalAlignment = VerticalAlignment.Top };
            TextBlock value = new TextBlock { Text = item.Value, Foreground = Brush("#C7CEC8"), FontSize = 11, TextWrapping = TextWrapping.Wrap };
            Grid.SetColumn(value, 1);
            grid.Children.Add(name);
            grid.Children.Add(value);
            border.Child = grid;
            metadataPanel.Children.Add(border);
        }

        private void AddTraceRow(ExecutionTrace trace)
        {
            Border border = new Border { BorderBrush = Brush("#202722"), BorderThickness = new Thickness(0, 0, 0, 1), Padding = new Thickness(9, 7, 9, 7) };
            Grid grid = new Grid();
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(30) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(145) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(125) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Border lane = new Border { Width = 21, Height = 21, BorderThickness = new Thickness(1), BorderBrush = LaneBrush(trace.Lane), HorizontalAlignment = HorizontalAlignment.Left };
            lane.Child = new TextBlock { Text = trace.Lane, Foreground = LaneBrush(trace.Lane), FontSize = 9, FontFamily = new FontFamily("Cascadia Mono, Consolas"), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
            TextBlock address = new TextBlock { Text = trace.Address, Foreground = Brush("#7D877F"), FontSize = 9, FontFamily = new FontFamily("Cascadia Mono, Consolas"), VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
            TextBlock instruction = new TextBlock { Text = trace.Instruction, Foreground = Brush("#C7CEC8"), FontSize = 9, FontFamily = new FontFamily("Cascadia Mono, Consolas"), VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
            TextBlock effect = new TextBlock { Text = trace.Effect, Foreground = Brush("#8D978F"), FontSize = 9, FontFamily = new FontFamily("Cascadia Mono, Consolas"), VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
            Grid.SetColumn(address, 1); Grid.SetColumn(instruction, 2); Grid.SetColumn(effect, 3);
            grid.Children.Add(lane); grid.Children.Add(address); grid.Children.Add(instruction); grid.Children.Add(effect);
            border.Child = grid;
            tracePanel.Children.Add(border);
        }

        private void OpenPackageDialog()
        {
            OpenFileDialog dialog = new OpenFileDialog();
            dialog.Title = "导入成品包";
            dialog.Filter = "成品包 (*.exe;*.apk;*.ipa)|*.exe;*.apk;*.ipa|所有文件 (*.*)|*.*";
            dialog.Multiselect = true;
            if (dialog.ShowDialog(Window) == true)
            {
                for (int index = 0; index < dialog.FileNames.Length; index++) AddPackage(dialog.FileNames[index], false, index == dialog.FileNames.Length - 1);
            }
        }

        private void OnDragOver(object sender, DragEventArgs args)
        {
            args.Effects = args.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
            args.Handled = true;
        }

        private void OnDrop(object sender, DragEventArgs args)
        {
            string[] files = args.Data.GetData(DataFormats.FileDrop) as string[];
            if (files == null) return;
            for (int index = 0; index < files.Length; index++) AddPackage(files[index], false, index == files.Length - 1);
        }

        private void OnPreviewKeyDown(object sender, KeyEventArgs args)
        {
            if (args.Key == Key.O && (Keyboard.Modifiers & ModifierKeys.Control) == ModifierKeys.Control)
            {
                OpenPackageDialog();
                args.Handled = true;
            }
        }

        private T Find<T>(string name) where T : FrameworkElement
        {
            T value = Window.FindName(name) as T;
            if (value == null) throw new InvalidOperationException("Native control is missing: " + name);
            return value;
        }

        private static SolidColorBrush Brush(string color)
        {
            return (SolidColorBrush)new BrushConverter().ConvertFromString(color);
        }

        private static SolidColorBrush ToneBrush(string tone, string accent)
        {
            if (tone == "ready") return Brush(accent);
            if (tone == "experimental") return Brush("#A993FF");
            if (tone == "missing") return Brush("#F1C45E");
            if (tone == "blocked") return Brush("#FF6675");
            return Brush("#8F9991");
        }

        private static SolidColorBrush KindBrush(ArtifactKind kind)
        {
            if (kind == ArtifactKind.WindowsExe) return Brush("#59B7FF");
            if (kind == ArtifactKind.AndroidApk) return Brush("#72E08B");
            if (kind == ArtifactKind.AppleIpa) return Brush("#A993FF");
            return Brush("#8F9991");
        }

        private static SolidColorBrush LaneBrush(string lane)
        {
            if (lane == "N") return Brush("#59B7FF");
            if (lane == "V") return Brush("#72E08B");
            if (lane == "E") return Brush("#B9FF57");
            if (lane == "H") return Brush("#A993FF");
            if (lane == "D") return Brush("#FF6675");
            return Brush("#657068");
        }

        private static string SystemGlyph(string id)
        {
            if (id == "windows") return "W";
            if (id == "android") return "A";
            if (id == "ios") return "i";
            if (id == "windowsphone") return "WP";
            return "J";
        }
    }
}
