### ocv.py script

Is used to fetch and update several OpenCV repositories (opencv, opencv_contrib, opencv_extra) at once using local mirror.

Installation:

1. Clone this repository to `~/.ocv` folder
2. Add line to `~/.bash_aliases`: `source ~/.ocv/bash_config`
3. Restart the shell
4. Run the `ocv --help` command

### Workspace layout

```
workspace
├── .template/ - folder with local mirrors for each repository
│   ├── files/ - this folder will be copied after new clone set is created
│   ├── opencv_contrib.git/ - local mirror
│   ├── opencv_extra.git/ - local mirror
│   └── opencv.git/ - local mirror
├── clone_set_1/ - one of clone sets
│   ├── build/ - build folder
│   ├── env.sh - script with useful environment variables (OPENCV_TEST_DATA_PATH, etc.)
│   ├── ocv.sublime-project - project for Sublime Text
│   ├── opencv/ - repository clone
│   ├── opencv_contrib/ - repository clone
│   └── opencv_extra/ - repository clone
├── clone_set_2/
│   └── ...
...
```

### Workflow

1. Init template folder

```.sh
mkdir ~/workspace
cd ~/workspace
ocv init
```

2. Create new clone set

```.sh
cd ~/workspace
ocv create test-something
```

3. Work with it

```.sh
cd ~/workspace/test-something

pushd opencv
# work with git repo
#...
popd

# open project in Sublime Text
subl ocv.sublime-project

pushd build
# build something
#...
source ../env.sh
# run tests using the test environment
#...
popd
```

4. Update if needed

```.sh
cd ~/workspace
ocv update test-something
```

5. Remove

```.sh
cd ~/workspace
rm -rf test-something
```

### Command line usage

Common arguments:

- `--template` - folder with the template (local mirrors), default is `.template`
- `-v` - verbose output
- `--slow` - do not use multithreaded work with repositories

#### Command `init`

This command will create new template. Use `--template` option to provide different destination name.

Example:

```.sh
cd ~/workspace
ocv init
```
this will create `~/workspace/.template` folder and mirror all GitHub repositories into it.

#### Command `create <dir>`

Creates new clone set. Use it like this:

```.sh
cd ~/workspace
ocv create my-test
```
this will create `my-test` folder with all repositories cloned into it.

The remotes to be created:

- `template` - points to local mirror, fetch-only
- `upstream` - points to the official OpenCV repository at GitHub, fetch-only
- `origin` - points to your GitHub clone, read-write

Options:

- `--force` - remove existing directory before creating
- `--branch <branch>` - checkout this branch after clone
- `--check <user:branch>` - create additional remote (named `checked`) and merge provided branch with default one.

#### Command `update <dir>`

Updates remotes for existing clone set. Will run `git fetch <remote>` for `template, upstream, origin` remotes.

#### Command `update_template`

Updates local mirrors in template folder. Will run `git remote update` for each local mirror repository.

### Template files

Create folder `.template/opencv` and put necessary files into it. This folder will be copied on top of newly created clone set.

For example, create following structure:

```.sh
workspace/.template/opencv
└── 3rdparty
    └── ippicv
        └── downloads
            └── linux-8b449a536a2157bcad08a2b9f266828b
                └── ippicv_linux_20141027.tgz
```

And these file will be put into each new clone folder.
