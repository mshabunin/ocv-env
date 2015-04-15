#!/usr/bin/python

from argparse import ArgumentParser
from re import search, MULTILINE
from subprocess import call, check_output, STDOUT
import os.path
from shutil import rmtree, copy2
import sys
import logging as log
import concurrent.futures
from tempfile import NamedTemporaryFile

# Some config here
the_upstream = "https://github.com/Itseez/%(repo)s.git"
the_custom_remote = "git@github.com:mshabunin/%(repo)s.git"
the_env_script = """# Add some useful environment variables here:
export OPENCV_TEST_DATA_PATH=%(path)s/opencv_extra/testdata
export ANDROID_NDK=/home/maksim/android-ndk-r10
export ANDROID_SDK=/home/maksim/android-sdk-linux
export PYTHONPATH=%(path)s/build/lib
"""

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
    out = NamedTemporaryFile()
    log.info("init %s", repo)
    call(["git", "clone", "--mirror", the_upstream % {'repo':repo}, t], stdout=out, stderr=STDOUT)
    call(["git", "-C", t, "remote", "set-url", "--push", "origin", "bad_url"], stdout=out, stderr=STDOUT)
    call(["git", "-C", t, "config", "--unset-all", "remote.origin.fetch"], stdout=out, stderr=STDOUT)
    call(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*"], stdout=out, stderr=STDOUT)
    call(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/tags/*:refs/tags/*"], stdout=out, stderr=STDOUT)
    log.debug("finished %s", repo)
    out.seek(0)
    return out.readlines()

def update_one_repo(repo, path):
    r = os.path.join(path, repo)
    out = NamedTemporaryFile()
    log.info("fetch %s", repo)
    for remote in ["template", "upstream", "origin"]:
        call(["git", "-C", r, "fetch", remote, "-v"], stdout=out, stderr=STDOUT)
    log.debug("finished %s", repo)
    out.seek(0)
    return out.readlines()

def init_one_repo(repo, template, path, branch, check_user=None, check_branch=None):
    r = os.path.abspath(os.path.join(path, repo))
    t = os.path.abspath(os.path.join(template, repo))
    out = NamedTemporaryFile()
    log.info("clone %s", repo)
    call(["git", "clone", t, r], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "remote", "add", "upstream", the_upstream % {'repo':repo}], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "remote", "set-url", "--push", "upstream", "bad_url"], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "remote", "add", "template", t + ".git"], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "remote", "set-url", "--push", "template", "bad_url"], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "remote", "set-url", "origin", the_custom_remote % {'repo':repo}], stdout=out, stderr=STDOUT)
    log.info("fetch %s/%s", repo, branch)
    call(["git", "-C", r, "fetch", "upstream", branch], stdout=out, stderr=STDOUT)
    call(["git", "-C", r, "checkout", "upstream/%s" % branch, "-B", branch], stdout=out, stderr=STDOUT)
    if not (check_user is None or check_branch is None):
        url = "git@github.com:%s/%s.git" % (check_user, repo)
        branches = check_output(["git", "ls-remote","--heads", url], universal_newlines=True, stderr=STDOUT)
        rx = search("refs/heads/%s$" % check_branch, branches, MULTILINE)
        if rx:
            log.info("checked remote: %s/%s:%s", check_user, repo, check_branch)
            call(["git", "-C", r, "remote", "add", "checked", url], stdout=out, stderr=STDOUT)
            call(["git", "-C", r, "remote", "set-url", "--push", "checked", "bad_url"], stdout=out, stderr=STDOUT)
            call(["git", "-C", r, "pull", "--no-edit", "checked", check_branch], stdout=out, stderr=STDOUT)
        else:
            log.info("skip check: %s/%s:%s", check_user, repo, check_branch)
    call(["git", "-C", r, "remote", "-v"], stdout=out, stderr=STDOUT)
    if os.path.exists(t):
        copy_template_files(repo, t, r)
    log.debug("finished %s", repo)
    out.seek(0)
    return out.readlines()

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
    with open(os.path.join(path, "env.sh"), "w") as f:
        f.write(the_env_script % {'path':os.path.abspath(path)})

def init_subl_project(path, repos):
    path = os.path.abspath(path)
    text = """# Sublime Text project for OpenCV
{
    "folders":
    [
        %s
    ]
}
"""
    sub = ",".join(['{"path": "%s"}' % r for r in repos])
    text = text % sub
    with open(os.path.join(path, "ocv.sublime-project"), "w") as f:
        f.write(text)

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

if __name__ == "__main__":
    commands = ["init", "create", "update"]
    repos = ["opencv", "opencv_contrib", "opencv_extra"]

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

    args = parser.parse_args()

    log.basicConfig(format='[%(levelname)s] %(message)s', level=log.DEBUG if args.v else log.WARNING)
    log.debug("Args: %s", args)

    # Create
    if args.cmd == "init":
        log.info("Init")
        if check_template_folder(args.template):
            log.error("Template directory already exists")
            exit(2)
        os.makedirs(os.path.abspath(args.template))
        if args.slow:
            for repo in repos:
                out = init_one_template(repo, args.template)
        else:
            with concurrent.futures.ProcessPoolExecutor() as e:
                def one_call(repo):
                    return init_one_template(repo, args.template)
                for out in e.map(one_call, repos):
                    log.debug("Output:\n" + "".join(["> " + line for line in out]))

    elif args.cmd == "create":
        log.info("Create")
        if not check_template_folder(args.template):
            log.error("Template directory does not exist")
            exit(2)
        if check_clone_folder(args.dir):
            if args.force:
                log.info("Removing existing directory '%s'", args.dir)
                rmtree(args.dir)
            else:
                log.error("Clone directory already exists '%s', you can use the --force option to remove it", args.dir)
                exit(2)
        user, branch = None, None
        if args.check:
            rx = search("^([^:]+):([^:]+)$", args.check)
            if rx:
                user, branch = rx.group(1), rx.group(2)
                log.debug("USER: %s, BRANCH: %s", user, branch)
            else:
                log.error("Bad argument: %s", args.check)
                log.error("Should be in form: <user>:<branch>")
                sys.exit(2)
        os.makedirs(os.path.join(args.dir, "build"))
        if args.slow:
            for repo in repos:
                out = init_one_repo(repo, args.template, args.dir, args.branch, user, branch)
                log.debug("Output:\n" + "".join(["> " + line for line in out]))
        else:
            with concurrent.futures.ProcessPoolExecutor() as e:
                def one_call(repo):
                    return init_one_repo(repo, args.template, args.dir, args.branch, user, branch)
                for out in e.map(one_call, repos):
                    log.debug("Output:\n" + "".join(["> " + line for line in out]))
        init_env_script(args.dir)
        init_subl_project(args.dir, [repos[0], repos[1]])
    elif args.cmd == "update":
        log.info("Update")
        if not check_template_folder(args.template):
            log.error("Template directory does not exist")
            exit(2)
        if not check_clone_folder(args.dir):
            log.error("Clone directory does not exist")
            exit(2)
        if args.slow:
            for repo in repos:
                out = update_one_repo(repo, args.dir)
                log.debug("Output:\n" + "".join(["\t" + line for line in out]))
        else:
            with concurrent.futures.ProcessPoolExecutor() as e:
                def one_call(repo):
                    return update_one_repo(repo, args.dir)
                for out in e.map(one_call, repos):
                    log.debug("Output:\n" + "".join(["\t" + line for line in out]))
    else:
        log.error("Bad command: %s", args.cmd)
        sys.exit(2)
