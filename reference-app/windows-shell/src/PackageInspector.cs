using System;
using System.Collections.Generic;
using System.IO;

namespace JidanOS
{
    public sealed class PackageInspector
    {
        private readonly List<IArtifactAdapter> adapters;

        public PackageInspector()
        {
            adapters = new List<IArtifactAdapter>();
            adapters.Add(new PeAdapter());
            adapters.Add(new ApkAdapter());
            adapters.Add(new IpaAdapter());
        }

        public ArtifactInfo Inspect(string path, bool builtIn)
        {
            if (String.IsNullOrWhiteSpace(path) || !File.Exists(path))
                throw new FileNotFoundException("Package file was not found.", path);

            FileInfo file = new FileInfo(path);
            if (file.Length > 4L * 1024L * 1024L * 1024L)
                throw new InvalidDataException("Packages larger than 4 GB are not accepted by this build.");

            for (int index = 0; index < adapters.Count; index++)
            {
                IArtifactAdapter adapter = adapters[index];
                if (adapter.Probe(path)) return adapter.Inspect(path, builtIn);
            }

            ArtifactInfo unknown = new ArtifactInfo();
            unknown.Path = path;
            unknown.Name = file.Name;
            unknown.Size = file.Length;
            unknown.Sha256 = RuntimeUtil.ComputeSha256(path);
            unknown.Metadata.Add(new MetadataItem("MAGIC", "No EXE/APK/IPA signature"));
            unknown.Metadata.Add(new MetadataItem("SHA-256", unknown.Sha256));
            return unknown;
        }

        public ExecutionResult Run(ArtifactInfo artifact, string action)
        {
            for (int index = 0; index < adapters.Count; index++)
            {
                if (adapters[index].Kind == artifact.Kind)
                    return adapters[index].Run(artifact, action);
            }
            return new ExecutionResult
            {
                Success = false,
                Title = "No runtime",
                Message = "No adapter can execute this package."
            };
        }
    }
}
