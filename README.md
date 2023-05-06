# ushell

## Quick start

(Tested on adelaide)

```shell
git clone --recurse-submodules https://github.com/TUM-DSE/ushell
cd unikraft-development
direnv allow # (or nix develop)
```

(in one terminal window)
```shell
cd apps/count
make menuconfig
make
just run
```

> Since .config contains the absolute path, we need to regenerate .config by running make menuconfig 

(in another terminal window)
```shell
cd apps/count
just attach
```

## Measurements / Evaluation

see [./misc/tests/README.md](./misc/tests/README.md)

## Docs
-[./misec/docs](./misc/docs)

## Branch
- [dev](https://github.com/TUM-DSE/ushell/tree/dev): Development branch
- [eurosys23](https://github.com/TUM-DSE/ushell/tree/eurosys23): Eurosys23 version

