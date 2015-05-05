#!/usr/bin/python

from argparse import ArgumentParser
from re import search, MULTILINE
from subprocess import call, check_output, STDOUT, CalledProcessError
import os.path
from shutil import rmtree, copy2
import sys
import logging as log
import concurrent.futures
from tempfile import NamedTemporaryFile

# Some config here
config = {

"repos": ["opencv", "opencv_contrib", "opencv_extra"],

"upstream": "https://github.com/Itseez/%(repo)s.git",

"custom": "git@github.com:mshabunin/%(repo)s.git",

"env_script":
"""# Some useful environment variables here
export OPENCV_TEST_DATA_PATH=%(path)s/opencv_extra/testdata
export ANDROID_NDK=/home/maksim/android-ndk-r10
export ANDROID_SDK=/home/maksim/android-sdk-linux
export PYTHONPATH=%(path)s/build/lib
""",

"subl_project":
"""{
    "folders":
    [
        {
            "path":"opencv"
        },
        {
            "path":"opencv_contrib"
        }
    ]
}
"""
}

class Executor:
    def __init__(self):
        self.out = NamedTemporaryFile()
    def call(self, cmd):
        call(cmd, stdout=self.out, stderr=STDOUT)
    def finish(self):
        self.out.seek(0)
        return self.out.readlines()

def init_one_template(repo, template):
    t = os.path.abspath(os.path.join(template, repo)) + ".git"
    e = Executor()
    log.info("%s: init template", repo)
    e.call(["git", "clone", "--mirror", config['upstream'] % {'repo':repo}, t])
    e.call(["git", "-C", t, "remote", "set-url", "--push", "origin", "bad_url"])
    e.call(["git", "-C", t, "config", "--unset-all", "remote.origin.fetch"])
    e.call(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*"])
    e.call(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/tags/*:refs/tags/*"])
    log.debug("%s: done", repo)
    return e.finish()

def update_one_repo(repo, path):
    r = os.path.join(path, repo)
    e = Executor()
    for remote in ["template", "upstream", "origin"]:
        log.info("%s: update %s", repo, remote)
        e.call(["git", "-C", r, "fetch", remote, "-v"])
    log.debug("%s: done", repo)
    return e.finish()

def update_template_repo(repo, path):
    r = os.path.join(path, repo) + ".git"
    e = Executor()
    log.info("%s: template update", repo)
    e.call(["git", "-C", r, "remote", "update", "--prune"])
    log.debug("%s: done", repo)
    return e.finish()

def is_branch_exist(repo, check_user, check_branch):
    url = "git@github.com:%s/%s.git" % (check_user, repo)
    try:
        branches = check_output(["git", "ls-remote","--heads", url], universal_newlines=True, stderr=STDOUT)
        rx = search("refs/heads/%s$" % check_branch, branches, MULTILINE)
    except CalledProcessError as e:
        log.warning("%s: no branch %s:%s - returned %s", repo, check_user, check_branch, e.returncode)
        return False
    if rx is None:
        log.warning("%s: no branch %s:%s - not found", repo, check_user, check_branch)
        return False
    return True

def init_one_repo(repo, template, path, branch, check_user=None, check_branch=None):
    r = os.path.abspath(os.path.join(path, repo))
    t = os.path.abspath(os.path.join(template, repo))
    e = Executor()
    log.info("%s: clone", repo)
    e.call(["git", "clone", t, r])
    e.call(["git", "-C", r, "remote", "add", "upstream", config['upstream'] % {'repo':repo}])
    e.call(["git", "-C", r, "remote", "set-url", "--push", "upstream", "bad_url"])
    e.call(["git", "-C", r, "remote", "add", "template", t + ".git"])
    e.call(["git", "-C", r, "remote", "set-url", "--push", "template", "bad_url"])
    e.call(["git", "-C", r, "remote", "set-url", "origin", config['custom'] % {'repo':repo}])
    log.info("%s: fetch %s", repo, branch)
    e.call(["git", "-C", r, "fetch", "upstream", branch])
    e.call(["git", "-C", r, "checkout", "upstream/%s" % branch, "-B", branch])
    if not (check_user is None or check_branch is None):
        if is_branch_exist(repo, check_user, check_branch):
            url = "git@github.com:%s/%s.git" % (check_user, repo)
            log.info("%s: pull %s:%s", repo, check_user, check_branch)
            e.call(["git", "-C", r, "remote", "add", "checked", url])
            e.call(["git", "-C", r, "remote", "set-url", "--push", "checked", "bad_url"])
            e.call(["git", "-C", r, "pull", "--no-edit", "checked", check_branch])
        else:
            log.info("%s: skip pull %s:%s", repo, check_user, check_branch)
    e.call(["git", "-C", r, "remote", "-v"])
    if os.path.exists(t):
        copy_template_files(repo, t, r)
    log.debug("%s: done", repo)
    return e.finish()

def copy_template_files(repo, src, dst):
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for f in files:
            s = os.path.join(src, rel, f)
            d = os.path.join(dst, rel, f)
            if not os.path.exists(d):
                log.debug("%s: copy %s", repo, rel)
                copy2(s, d)
        for f in dirs:
            d = os.path.join(dst, rel, f)
            if not os.path.exists(d):
                log.debug("%s: create %s", repo, d)
                os.mkdir(d)

def init_env_script(path):
    with open(os.path.join(os.path.abspath(path), "env.sh"), "w") as f:
        f.write(config['env_script'] % {'path':os.path.abspath(path)})

def init_subl_project(path):
    with open(os.path.join(os.path.abspath(path), "ocv.sublime-project"), "w") as f:
        f.write(config['subl_project'])

def check_template_folder(folder):
    # TODO: also check contains - mirrors
    if not os.path.exists(folder):
        return False
    return True

def check_clone_folder(folder):
    # TODO: check contains - opencv/opencv_contrib/opencv_extra
    if not os.path.exists(folder):
        return False
    return True

class Fail(Exception):
    def __init__(self, text=None):
        self.t = text
    def __str__(self):
        return "ERROR" if self.t is None else self.t

class Worker:
    def __init__(self, repos, template, slow):
        self.repos = repos
        self.template = template
        self.slow = slow

    #-----------------------
    # Command handlers
    #-----------------------
    def init(self):
        log.info("Init")
        if check_template_folder(self.template):
            raise Fail("Template directory already exists")
        os.makedirs(os.path.abspath(self.template))
        self.multi_run(lambda repo: init_one_template(repo, self.template))

    def create(self, dir, check, checkout_branch, force):
        log.info("Create")
        if not check_template_folder(self.template):
            raise Fail("Template directory does not exist")
        if check_clone_folder(dir):
            if force:
                log.info("Removing existing directory '%s'", dir)
                rmtree(dir)
            else:
                raise Fail("Clone directory already exists '%s', you can use the --force option to remove it" % dir)
        user, branch = None, None
        if check:
            rx = search("^([^:]+):([^:]+)$", check)
            if rx:
                user, branch = rx.group(1), rx.group(2)
                log.debug("USER: %s, BRANCH: %s", user, branch)
            else:
                raise Fail("Bad argument: %s, should be in form user:branch" % check)
        os.makedirs(os.path.join(dir, "build"))
        self.multi_run(lambda repo: init_one_repo(repo, self.template, dir, checkout_branch, user, branch))
        init_env_script(dir)
        init_subl_project(dir)

    def update(self, dir):
        log.info("Update")
        if not check_template_folder(self.template):
            raise Fail("Template directory does not exist")
        if not check_clone_folder(dir):
            raise Fail("Clone directory does not exist")
        self.multi_run(lambda repo: update_one_repo(repo, dir))

    def update_template(self):
        log.info("Update")
        if not check_template_folder(self.template):
            raise Fail("Template directory does not exist")
        self.multi_run(lambda repo: update_template_repo(repo, self.template))

    #-----------------------
    # Utility methods
    #-----------------------
    def multi_run(self, func):
        if self.slow:
            for out in map(func, self.repos):
                log.debug("Output:\n" + "".join(["> " + line for line in out]))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as e:
                for out in e.map(func, self.repos):
                    log.debug("Output:\n" + "".join(["> " + line for line in out]))

#----------------------
# Main
#----------------------
if __name__ == "__main__":
    parser = ArgumentParser(description = 'Command-line tool to work with OpenCV dev environment')
    parser.add_argument('--template', default='.template', metavar='dir', help='Template dir with local mirrors (default is ".template")')
    parser.add_argument('-v', action='store_true', help='Verbose logging')
    parser.add_argument('--slow', action='store_true', help='Do not use multiprocessing')
    sub = parser.add_subparsers(title='Commands', dest='cmd')

    # Init new template folder
    parser_init = sub.add_parser('init', help='Init fresh template')

    # Create new clone
    parser_create = sub.add_parser('create', help='Create new clone set')
    parser_create.add_argument('dir', metavar='dir', help='Directory for clone set')
    parser_create.add_argument('--check', metavar='user:branch', help='GitHub user/branch to add as checked remote')
    parser_create.add_argument('--force', action='store_true', help='Remove existing repository')
    parser_create.add_argument('--branch', metavar='b', default='master', help='Branch to checkout by default')

    # Update existing clone
    parser_update = sub.add_parser('update', help='Update existing clone set')
    parser_update.add_argument('dir', metavar='dir', help='Directory containing the clone set to update')

    # Update template
    parser_update_template = sub.add_parser('update_template', help='Update template state')

    # TODO:
    # - build (creates some scripts: debug/release, shared/static, +install, docs)
    #   ??? or copy some files from template folder
    # - clean build (rm -rf build/*), clean repos (reset --hard, clean -f)

    args = parser.parse_args()

    # log.basicConfig(format='[%(levelname)s] %(message)s', level=log.DEBUG if args.v else log.WARNING)
    if args.v:
        log.basicConfig(format='[%(levelno)s] %(message)s', level=log.DEBUG)
    else:
        log.basicConfig(format='%(message)s', level=log.WARNING)

    log.debug("Args: %s", args)

    try:
        w = Worker(config['repos'], args.template, args.slow)
        if args.cmd == "init":
            w.init()
        elif args.cmd == "create":
            w.create(args.dir, args.check, args.branch, args.force)
        elif args.cmd == "update":
            w.update(args.dir)
        elif args.cmd == "update_template":
            w.update_template()
        else:
            raise Fail("Bad command: %s" % args.cmd)
    except Fail as e:
        log.error("Fail: %s", e)
        sys.exit(1)
