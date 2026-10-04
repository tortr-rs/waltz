{
  description = "waltz dev shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      devShells.${system}.default = pkgs.mkShell {
        nativeBuildInputs = with pkgs; [
          pkg-config
          cargo
          rustc
        ];
        buildInputs = with pkgs; [
          wayland
          wayland-protocols
          libxkbcommon
          libGL
          # add if the build asks for them:
          # xorg.libX11 xorg.libXcursor xorg.libXrandr xorg.libXi
          # vulkan-loader
        ];

        # Needed at runtime so the binary can dlopen wayland/GL/etc.
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
          pkgs.wayland
          pkgs.libxkbcommon
          pkgs.libGL
        ];
      };
    };
}
