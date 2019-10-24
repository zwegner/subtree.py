#!/usr/bin/env python3
import argparse
import collections
import contextlib
import copy
import os
import subprocess
import sys

def error(msg):
    print(msg)
    sys.exit(1)

def run(args, check=False):
    shell = False
    if isinstance(args, str):
        shell = True
    if check:
        return subprocess.check_call(args, shell=shell)
    proc = subprocess.run(args, shell=shell, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
    return (proc.returncode, proc.stdout, proc.stderr)

def has_local_changes():
    if (run('git diff --quiet')[0] or run('git diff --cached --quiet')[0]):
        return True
    return False

@contextlib.contextmanager
def autostash():
    try:
        if has_local_changes():
            print('Auto-stashing changes...')
            (code, out, err) = run('git stash create autostash')
            if code == 0:
                stash = out.decode('ascii').strip()
                (code, out, err) = run('git reset --hard')
                if code:
                    error('Failed to reset, but stashed at %s' % stash)

                yield

                (code, out, err) = run(['git', 'stash', 'apply', stash])
                if code:
                    print(out)
                    print(err)
                    print('Error applying autostash. Saving to stashes...')
                    (code, out, err) = run(['git', 'stash', 'store', '-m', 'autostash',
                        '-q', stash])
                    if code:
                        error('Failed to store stash %s!' % stash)
        else:
            yield
    except:
        print('FAILURE! stash=%s' % stash)
        raise

def cd_to_root():
    (code, out, err) = run('git worktree list --porcelain')
    line = out.decode('utf-8').splitlines()[0]
    _, root = line.split(' ', 1)
    os.chdir(root)

def read_db():
    (code, out, err) = run('git config --get-regexp "subtree\\."')
    assert code == 0
    subtrees = collections.defaultdict(dict)
    for line in out.decode('utf-8').splitlines():
        key, value = line.split()
        sub, name, key = key.split('.')
        subtrees[name][key] = value

    return {'subtrees': dict(subtrees)}

def write_db(old_db, db):
    for name, subtree in db['subtrees'].items():
        # Only write new/updated entries
        if subtree == old_db.get(name):
            continue

        for key, value in subtree.items():
            key = 'subtree.%s.%s' % (name, key)
            (code, out, err) = run(['git', 'config', '--replace-all', key, value])
            assert code == 0

def main():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(title='subcommands', required=True)
    def add_cmd(cmd, *args):
        p = subparser.add_parser(cmd)
        p.set_defaults(cmd=cmd)
        for arg in args:
            if isinstance(arg, dict):
                p.add_argument(**arg)
            else:
                p.add_argument(arg)

    add_cmd('list')
    add_cmd('add', 'alias', 'prefix', 'url',
            {'dest': 'branch', 'default': 'master', 'nargs': '?'})
    add_cmd('push', 'alias')
    add_cmd('pull', 'alias')
    add_cmd('split', 'alias')

    args = parser.parse_args(sys.argv[1:])

    db = read_db()
    old_db = copy.deepcopy(db)

    if args.cmd == 'list':
        for name, subtree in db['subtrees'].items():
            print('%s:' % name)
            for key, value in subtree.items():
                print('    %s = %s' % (key, value))

    # Most commands need to autostash and cd to root
    elif args.cmd in ('add', 'push', 'pull', 'split'):
        cd_to_root()
        with autostash():
            if args.cmd == 'add':
                run(['git', 'subtree', 'add', '--squash',
                    '--prefix', args.prefix, args.url, args.branch], check=True)
                assert args.alias not in db['subtrees']
                db['subtrees'][args.alias] = {'prefix': args.prefix,
                        'url': args.url, 'branch': args.branch}

            elif args.cmd in ('push', 'pull'):
                subtree = db['subtrees'][args.alias]
                run(['git', 'subtree', args.cmd, '--squash',
                    '--prefix', subtree['prefix'],
                    subtree['url'], subtree['branch']], check=True)

            elif args.cmd == 'split':
                subtree = db['subtrees'][args.alias]
                run(['git', 'subtree', 'split', '--prefix', subtree['prefix']],
                        check=True)

    else:
        assert False

    write_db(old_db, db)

if __name__ == '__main__':
    main()
