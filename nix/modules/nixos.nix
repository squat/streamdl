{
  self,
}:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  inherit (lib)
    mkEnableOption
    mkPackageOption
    mkOption
    maintainers
    ;
  inherit (lib.types)
    bool
    path
    port
    str
    submodule
    ;
  cfg = config.services.streamdl;
  settingsFormat = pkgs.formats.json { };
in
{
  options = {
    services.streamdl = {
      enable = mkEnableOption "streamdl -- Streamlit frontend for spotDL";

      package = mkPackageOption self.packages.${pkgs.stdenv.system} "streamdl" {
        default = "default";
        pkgsText = "streamdl.packages.\${pkgs.stdenv.system}";
      };

      spotDLConfig = mkOption {
        type = submodule {
          freeformType = settingsFormat.type;
        };
        default = { };
        example = { };
        description = "Configuration for spotDL, see <https://spotdl.readthedocs.io/en/latest/usage/#config-file> for supported values.";
      };

      spotDLConfigFile = mkOption {
        type = path;
        example = "/var/lib/streamdl.json";
        description = "Configuration file for spotDL, see <https://spotdl.readthedocs.io/en/latest/usage/#config-file> for supported values. Overrides `spotDLConfig`.";
      };

      user = mkOption {
        type = str;
        default = "streamdl";
        description = "User under which streamdl runs.";
      };

      group = mkOption {
        type = str;
        default = "streamdl";
        description = "Group under which streamdl runs.";
      };

      address = mkOption {
        default = "127.0.0.1";
        description = "Address to run streamdl on.";
        type = str;
      };

      port = mkOption {
        default = 8501;
        description = "Port to run streamdl on.";
        type = port;
      };

      gatherUsageStats = mkOption {
        default = false;
        description = "Whether to send usage statistics to Streamlit.";
        type = bool;
      };

      openFirewall = mkOption {
        type = bool;
        default = false;
        description = "Whether to open the TCP port in the firewall";
      };

      workingDirectory = mkOption {
        type = path;
        default = "/var/lib/streamdl";
        description = "Directory to store caches.";
      };

      dataDirectory = mkOption {
        type = path;
        default = cfg.workingDirectory;
        example = "/mnt/music";
        description = "Directory to store music.";
      };
    };
  };

  config =
    let
      inherit (lib)
        mkIf
        ;
      configFile =
        if cfg.spotDLConfigFile != null then
          cfg.spotDLConfigFile
        else
          settingsFormat.generate "config.json" cfg.spotdlConfig;
    in
    mkIf cfg.enable {
      systemd = {
        tmpfiles.settings.streamdl = {
          "${cfg.dataDirectory}"."d" = {
            mode = "755";
            inherit (cfg) user group;
          };
          "${cfg.workingDirectory}/spotdl"."d" = {
            mode = "700";
            inherit (cfg) user group;
          };
        }
        // (
          if cfg.workingDirectory != cfg.dataDirectory then
            {
              "${cfg.workingDirectory}"."d" = {
                mode = "700";
                inherit (cfg) user group;
              };
            }
          else
            { }
        );
        services.streamdl = {
          description = "streamdl -- Streamlit frontend for spotDL";
          after = [ "network.target" ];
          wantedBy = [ "multi-user.target" ];
          environment = {
            XDG_DATA_HOME = "${cfg.workingDirectory}";
          };
          serviceConfig = {
            ExecStart = ''
              ${cfg.package}/bin/streamdl --browser.gatherUsageStats ${
                if cfg.gatherUsageStats then "true" else "false"
              } --server.address ${cfg.address} --server.port ${toString cfg.port} --server.headless true -- --config ${configFile}
            '';
            User = cfg.user;
            Group = cfg.group;
            WorkingDirectory = cfg.dataDirectory;
            RuntimeDirectory = "streamdl";
            RootDirectory = "/run/streamdl";
            ReadWritePaths = "";
            BindPaths = [
              cfg.workingDirectory
              cfg.dataDirectory
            ];
            BindReadOnlyPaths = [
              configFile
              # streamdl uses online services.
              "${config.security.pki.caBundle}:/etc/ssl/certs/ca-certificates.crt"
              builtins.storeDir
              "/etc"
            ]
            ++ lib.optionals config.services.resolved.enable [
              "/run/systemd/resolve/stub-resolv.conf"
              "/run/systemd/resolve/resolv.conf"
            ];
          };
        };
      };

      users.users = mkIf (cfg.user == "streamdl") {
        streamdl = {
          inherit (cfg) group;
          isSystemUser = true;
        };
      };

      users.groups = mkIf (cfg.group == "streamdl") { streamdl = { }; };

      networking.firewall.allowedTCPPorts = mkIf cfg.openFirewall [ cfg.port ];
    };
  meta.maintainers = with maintainers; [ squat ];
}
