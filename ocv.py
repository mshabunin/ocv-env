#!/usr/bin/python

from argparse import ArgumentParser
from re import search, MULTILINE
from subprocess import check_output, STDOUT, CalledProcessError
import os.path
from shutil import rmtree, copy2, move
import sys
import logging as log
import concurrent.futures
from tempfile import NamedTemporaryFile

def get_upstream_url(user, repo):
    return "https://github.com/%(user)s/%(repo)s.git" % locals()

def get_user_copy_url(user, repo):
    return "git@github.com:%(user)s/%(repo)s.git" % locals()

def execute(cmd):
    try:
        res = check_output(cmd, stderr = STDOUT).decode("latin-1").splitlines()
    except CalledProcessError as e:
        return e.output.decode("latin-1").splitlines()
    return res

def init_one_template(repo, template, upstream_user):
    t = os.path.abspath(os.path.join(template, repo)) + ".git"
    out = []
    log.info("%s: init template", repo)
    out += execute(["git", "clone", "--mirror", get_upstream_url(upstream_user, repo), t])
    out += execute(["git", "-C", t, "remote", "set-url", "--push", "origin", "bad_url"])
    out += execute(["git", "-C", t, "config", "--unset-all", "remote.origin.fetch"])
    out += execute(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/heads/*:refs/heads/*"])
    out += execute(["git", "-C", t, "config", "--add", "remote.origin.fetch", "+refs/tags/*:refs/tags/*"])
    log.debug("%s: done", repo)
    return out, repo

def update_one_repo(repo, path):
    r = os.path.join(path, repo)
    out = []
    for remote in ["template", "upstream", "origin"]:
        log.info("%s: update %s", repo, remote)
        out += execute(["git", "-C", r, "fetch", remote, "-v"])
    log.debug("%s: done", repo)
    return out, repo

def update_template_repo(repo, path):
    r = os.path.join(path, repo) + ".git"
    log.info("%s: template update", repo)
    out = execute(["git", "-C", r, "remote", "update", "--prune"])
    log.debug("%s: done", repo)
    return out, repo

def is_branch_exist(repo, check_user, check_branch):
    url = get_user_copy_url(check_user, repo)
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

def is_local_branch_eist(r, branch):
    out = execute(["git", "-C", r, "branch", "-a"])

def init_one_repo(repo, template, path, branch, upstream_user, user, check_user=None, check_branch=None):
    r = os.path.abspath(os.path.join(path, repo))
    t = os.path.abspath(os.path.join(template, repo))
    out = []
    log.info("%s: clone", repo)
    out += execute(["git", "clone", t, r])
    out += execute(["git", "-C", r, "remote", "add", "upstream", get_upstream_url(upstream_user, repo)])
    out += execute(["git", "-C", r, "remote", "set-url", "--push", "upstream", "bad_url"])
    out += execute(["git", "-C", r, "remote", "add", "template", t + ".git"])
    out += execute(["git", "-C", r, "remote", "set-url", "--push", "template", "bad_url"])
    out += execute(["git", "-C", r, "remote", "set-url", "origin", get_user_copy_url(user, repo)])
    log.info("%s: fetch %s", repo, branch)
    out += execute(["git", "-C", r, "fetch", "upstream", branch])
    out += execute(["git", "-C", r, "checkout", "upstream/%s" % branch, "-B", branch])
    if not (check_user is None or check_branch is None):
        if is_branch_exist(repo, check_user, check_branch):
            url = get_user_copy_url(check_user, repo)
            log.info("%s: pull %s:%s", repo, check_user, check_branch)
            out += execute(["git", "-C", r, "remote", "add", "checked", url])
            out += execute(["git", "-C", r, "remote", "set-url", "--push", "checked", "bad_url"])
            out += execute(["git", "-C", r, "pull", "--no-edit", "checked", check_branch])
        else:
            log.info("%s: skip pull %s:%s", repo, check_user, check_branch)
    out += execute(["git", "-C", r, "remote", "-v"])
    log.debug("%s: done", repo)
    return out, repo

def checkout_one_repo(repo, path, branch):
    r = os.path.abspath(os.path.join(path, repo))
    log.info("%s: checkout %s", repo, branch)
    out = execute(["git", "-C", r, "checkout", branch])
    return out, repo


def copy_files(src, dst):
    log.debug("Copying files from %s", src)
    for path, _, names in os.walk(src):
        for name in names:
            # Determine src and dst paths
            input_file = os.path.join(path, name)
            output_dir = os.path.join(dst, os.path.relpath(path, src))
            output_file = os.path.normpath(os.path.join(output_dir, name))
            # Create folder and copy file into it
            try:
                os.makedirs(output_dir)
            except Exception as e:
                pass
            copy2(input_file, output_file)
            # Rename '*.in' files and replace template strings
            if output_file[-3:] == ".in":
                fixed_file = output_file[:-3]
                move(output_file, fixed_file)
                output_file = fixed_file
                with open(output_file, "r") as f:
                    lines = f.readlines()
                lines = [l % {'path':os.path.abspath(dst)} for l in lines]
                with open(output_file, "w") as f:
                    f.writelines(lines)
            # Done
            log.debug("One file: %s", os.path.relpath(output_file, dst))

def check_template_folder(folder):
    # TODO: also check contains - mirrors
    if not os.path.exists(folder):
        return False
    return True

def check_clone_folder(folder):
    if not os.path.exists(folder):
        return False
    return True

class Fail(Exception):
    def __init__(self, text=None):
        self.t = text
    def __str__(self):
        return "ERROR" if self.t is None else self.t

class Worker:
    def __init__(self, repos, template, slow, upstream_user, user):
        self.repos = repos
        self.template = template
        self.slow = slow
        self.upstream_user = upstream_user
        self.user = user

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
        self.multi_run(lambda repo: init_one_repo(repo, self.template, dir, checkout_branch, self.upstream_user, self.user, user, branch))
        copy_files(os.path.join(self.template, "files"), dir)

    def update(self, dir):
        log.info("Update")
        if not check_template_folder(self.template):
            raise Fail("Template directory does not exist")
        if not check_clone_folder(dir):
            raise Fail("Clone directory does not exist")
        self.multi_run(lambda repo: update_one_repo(repo, dir))

    def checkout(self, dir, branch):
        log.info("Checkout")
        if not check_clone_folder(dir):
            raise Fail("Clone directory does not exist")
        self.multi_run(lambda repo: checkout_one_repo(repo, dir, branch))

    def update_template(self):
        log.info("Update")
        if not check_template_folder(self.template):
            raise Fail("Template directory does not exist")
        self.multi_run(lambda repo: update_template_repo(repo, self.template))

    def status(self):
        log.info("Status")
        for d in os.listdir("."):
            if not os.path.isfile(d) and os.path.exists(d):
                log.info("\n=== Directory '%s' ===", d)
                for repo in self.repos:
                    if os.path.exists(os.path.join(d, repo)):
                        # determine branch
                        out = execute(["git", "-C", os.path.join(d, repo), "rev-parse", "--abbrev-ref", "HEAD"])
                        branch = "".join(out).strip()
                        # determine file status
                        out = execute(["git", "-C", os.path.join(d, repo), "status", "--porcelain"])
                        if len(out) > 0:
                            status = "\n".join(["|| " + line for line in out]).strip()
                            log.info("%(repo)s @ %(branch)s%(status)s" % locals())
                        else:
                            log.info("%(repo)s @ %(branch)s" % locals())
                    else:
                        log.info("%(repo)s - does not exist" % locals())

    #-----------------------
    # Utility methods
    #-----------------------
    def multi_run(self, func):
        if self.slow:
            theMap = map
        else:
            theMap = concurrent.futures.ThreadPoolExecutor(max_workers=3).map
        for out, r in theMap(func, self.repos):
            log.debug("\n=== Output [%s] ===\n" % r + "\n".join(["|| " + line for line in out]))

#----------------------
# Main
#----------------------
if __name__ == "__main__":
    parser = ArgumentParser(description = 'Command-line tool to work with OpenCV dev environment')
    parser.add_argument('--template', default='.template', metavar='dir', help='Template dir with local mirrors (default is ".template")')
    parser.add_argument('-v', action='store_true', help='Verbose logging')
    parser.add_argument('--slow', action='store_true', help='Do not use multiprocessing')
    parser.add_argument('--user', required=True, help="Main user account")
    parser.add_argument('--upstream', required=True, help="Upstream user account")
    parser.add_argument('--repos', required=True, help="Comma separated repository list")
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

    # Overview
    parser_init = sub.add_parser('status', help='Show current folder overview')

    # Checkout
    parser_checkout = sub.add_parser('checkout', help='Update current files state')
    parser_checkout.add_argument('dir', metavar='dir', help='Directory containing the clone set to update')
    parser_checkout.add_argument('branch', metavar='branch', help='Branch to checkout: will be passed to git')

    # TODO:
    # - build (creates some scripts: debug/release, shared/static, +install, docs)
    #   ??? or copy some files from template folder
    # - clean build (rm -rf build/*), clean repos (reset --hard, clean -f)

    args = parser.parse_args()

    # log.basicConfig(format='[%(levelname)s] %(message)s', level=log.DEBUG if args.v else log.WARNING)
    if args.v:
        # log.basicConfig(format='[%(levelno)s] %(message)s', level=log.DEBUG)
        log.basicConfig(format='%(message)s', level=log.DEBUG)
    else:
        log.basicConfig(format='%(message)s', level=log.INFO)

    log.debug("Args: %s", args)

    try:
        w = Worker(args.repos.split(","), args.template, args.slow, args.upstream, args.user)
        if args.cmd == "init":
            w.init()
        elif args.cmd == "create":
            w.create(args.dir, args.check, args.branch, args.force)
        elif args.cmd == "update":
            w.update(args.dir)
        elif args.cmd == "update_template":
            w.update_template()
        elif args.cmd == "status":
            w.status()
        elif args.cmd == "checkout":
            w.checkout(args.dir, args.branch)
        else:
            raise Fail("Bad command: %s" % args.cmd)
    except Fail as e:
        log.error("Fail: %s", e)
        sys.exit(1)
