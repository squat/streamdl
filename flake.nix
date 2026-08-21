{
  description = "A Streamlit frontend for spotDL";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    git-hooks-nix = {
      url = "github:cachix/git-hooks.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.git-hooks-nix.flakeModule
      ];

      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      flake = {
        overlays = {
          default = inputs.self.overlays.streamdl;
          streamdl = final: prev: {
            streamdl = inputs.self.packages.${prev.system}.streamdl;
          };
        };

        nixosModules = {
          default = inputs.self.nixosModules.streamdl;
          streamdl = import ./nix/modules/nixos.nix { inherit (inputs) self; };
        };
      };

      perSystem =
        {
          pkgs,
          system,
          config,
          self,
          ...
        }:
        let
          workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
          pyprojectOverrides = final: prev: {
            jaconv = prev.jaconv.overrideAttrs (old: {
              buildInputs = (old.buildInputs or [ ]) ++ final.resolveBuildSystem ({ setuptools = [ ]; });
            });
          };
          overlay = workspace.mkPyprojectOverlay {
            sourcePreference = "wheel";
          };
          pythonSet =
            (pkgs.callPackage inputs.pyproject-nix.build.packages {
              python = pkgs.python3;
            }).overrideScope
              (
                pkgs.lib.composeManyExtensions [
                  inputs.pyproject-build-systems.overlays.wheel
                  overlay
                  pyprojectOverrides
                ]
              );

        in
        {
          packages = {
            default = pkgs.symlinkJoin {
              name = "streamdl";
              paths = [
                ((pkgs.callPackages inputs.pyproject-nix.build.util { }).mkApplication {
                  venv = pythonSet.mkVirtualEnv "streamdl" workspace.deps.default;
                  package = pythonSet.streamdl;
                })
                pkgs.ffmpeg
              ];
              buildInputs = [ pkgs.makeWrapper ];
              postBuild = "wrapProgram $out/bin/streamdl --prefix PATH : $out/bin";
            };
          };

          pre-commit = {
            check.enable = true;
            settings = {
              src = ./.;
              hooks = {
                actionlint.enable = true;
                nixfmt-rfc-style.enable = true;
                ruff.enable = true;
                ruff-format.enable = true;
              };
            };
          };

          devShells =
            let
              editableOverlay = workspace.mkEditablePyprojectOverlay {
                root = "$REPO_ROOT";
              };
              editablePythonSet = pythonSet.overrideScope (
                pkgs.lib.composeManyExtensions [
                  editableOverlay
                  pyprojectOverrides
                ]
              );
              virtualenv = editablePythonSet.mkVirtualEnv "streamdl" workspace.deps.all;
            in
            {
              default = pkgs.mkShell {
                shellHook = config.pre-commit.devShell.shellHook + ''
                  unset PYTHONPATH
                  export REPO_ROOT=$(git rev-parse --show-toplevel)
                  . ${virtualenv}/bin/activate
                  export PYTHONPATH="$VIRTUAL_ENV/lib/python${editablePythonSet.python.pythonVersion}/site-packages:$PYTHONPATH"
                '';
                packages =
                  with pkgs;
                  [
                    virtualenv
                    uv
                    ffmpeg
                  ]
                  ++ config.pre-commit.settings.enabledPackages;
                env = {
                  UV_NO_SYNC = "1";
                  UV_PYTHON = editablePythonSet.python.interpreter;
                  UV_PYTHON_DOWNLOADS = "never";
                };
              };
            };
        };
    };
}
