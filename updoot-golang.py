#!/bin/python3

import os
import shutil
import tempfile
import sys
import requests
import platform
import hashlib
import argparse

# TODO: detect from environment or `go env GOROOT` or shutil.which() if set to None
GOROOT = '/usr/local/go'

GOWEBSITE = 'https://golang.org'

# dicts map from `platform` methods to remote data
# TODO: support more OS's/arch's

OS_DICT = {
    'Linux': 'linux',
}

ARCH_DICT = {
    'x86_64': 'amd64',
    'aarch64': 'arm64',
}


def detect_platform():
    def platform_unsupported():
        print('this OS and/or architecture is not supported by updoot-golang :(')
        print('try looking at OS_DICT and ARCH_DICT')
        print('if OS_DICT doesn\'t have your OS then it would need support in install_file')
        print('but if it\'s just ARCH_DICT you can probably just add your architecture to the list')
        print('unless it\'s something weird they don\'t build Go for, then you\'ll just get a ~*~different error~*~')
        print('if you fix this for yourself, plz send me a PR (https://github.com/Quantaly/updoot-golang/)')
        print('especially if you add support for your OS')
        sys.exit(1)

    opsys = platform.system()
    if opsys in OS_DICT:
        opsys = OS_DICT[opsys]
    else:
        platform_unsupported()

    arch = platform.machine()
    if arch in ARCH_DICT:
        arch = ARCH_DICT[arch]
    else:
        platform_unsupported()

    return opsys, arch


def get_versions(all, unstable):
    url = '{}/dl/?mode=json'.format(GOWEBSITE)
    if all or unstable:
        url += '&include=all'

    resp = requests.get(url)
    if resp.status_code != 200:
        print('remote returned status {}'.format(resp.status_code))
        sys.exit(1)
    versions = resp.json()

    if all and not unstable:
        versions = list(filter(lambda v: v.stable, versions))
    return versions


def install_file(file):
    # TODO check installed version before downloading
    print('+ Installing {}'.format(file['version']))

    olddir = tempfile.TemporaryDirectory()
    try:
        shutil.move(GOROOT, olddir.name)
    except IOError as e:
        olddir.cleanup()
        olddir = None
        if e.errno == 2:
            # no old version to remove
            print('No existing Go installation at {}, ignoring'.format(GOROOT))
        else:
            print('Failed to remove old Go installation:')
            print(e)
            if e.errno == 13:
                # permission denied
                print('(maybe you need to be root?)')
            sys.exit(1)

    download = tempfile.NamedTemporaryFile(delete=False)
    download_hash = hashlib.sha256()
    download_resp = requests.get(
        '{}/dl/{}'.format(GOWEBSITE, file['filename']), stream=True)
    if download_resp.status_code != 200:
        print('remote returned status {}'.format(download_resp.status_code))
        download.delete = True
        download.close()
        sys.exit(1)

    print('Downloading archive...')
    # TODO provide some form of progress indicator
    # maybe use curl if available?
    for chunk in download_resp.iter_content(65536):
        # if you don't specify a chunk_size then iter_content apparently reads bytes one at a time
        # why the hecc is that the default behavior?? who would ever want that?? who knows
        # print(len(chunk))
        download.write(chunk)
        download_hash.update(chunk)
    print('Archive downloaded.')
    download.close()
    if download_hash.hexdigest() == file['sha256']:
        print('Verification succeeded.')
    else:
        shutil.move(os.path.join(olddir.name, os.path.basename(GOROOT)), GOROOT)
        print('Verification failed!')
        print('Expected hash: {}'.format(file['sha256']))
        print('Actual hash: {}'.format(download_hash.hexdigest()))
        print('tbh I have no idea how this would happen')
        print('maybe some sort of weird network problem?')
        print('presumably they would provide the hash for a reason')
        print('so let\'s not install this for whatever that reason is')
        print('if you want to check out the file, here\'s the path:')
        print(download.name)
        print('otherwise try again later I guess')
        sys.exit(1)

    print('Extracting archive...')
    extract_dir = tempfile.TemporaryDirectory()
    if file['filename'].endswith('.tar.gz'):
        shutil.unpack_archive(download.name, extract_dir.name, 'gztar')
    else:
        shutil.unpack_archive(download.name, extract_dir.name, 'zip')
    print('Archive extracted.')
    shutil.move(os.path.join(extract_dir.name, "go"), GOROOT)
    print('Successfully installed {}.'.format(file['version']))

    os.remove(download.name)
    if olddir != None:
        # takes the old Go installation with it, sayonara
        olddir.cleanup()


# command entrypoints

def install_latest(args):
    opsys, arch = detect_platform()
    versions = get_versions(args.all, args.unstable)

    # FIXME actually scan to find the latest version; with unstable, may not be at the top
    for file in versions[0]['files']:
        if file['kind'] == 'archive' and file['os'] == opsys and file['arch'] == arch:
            install_file(file)
            break
    else:
        print('no suitable Go build was found :(')
        print('maybe they stopped building Go for you at some point :( :( :(')
        sys.exit(1)


def install(args):
    print('install')
    print(args)
    raise NotImplementedError()


def list_versions(args):
    print('list_versions')
    print(args)
    raise NotImplementedError()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manages a Go installation.',
                                     epilog='By default, this tool will only work with recent stable versions of Go unless otherwise specified.')
    parser.set_defaults(func=install_latest, all=False, unstable=False)
    subparsers = parser.add_subparsers()

    parser_install_latest = subparsers.add_parser(
        'install-latest', help='(default) Install the latest stable version')
    # parser_install_latest.set_defaults(func=install_latest) # already the global default
    parser_install_latest.add_argument('-u', '--unstable', action='store_true',
                                       help='install the latest unstable version')

    parser_install = subparsers.add_parser(
        'install', help='Install a specified version')
    parser_install.set_defaults(func=install)

    parser_list = subparsers.add_parser('list', help='List recent stable versions')
    parser_list.set_defaults(func=list_versions)
    parser_list.add_argument('-a', '--all', action='store_true',
                             help='list all stable versions')
    parser_list.add_argument('-u', '--unstable', action='store_true',
                             help='list all stable and unstable versions')

    args = parser.parse_args()
    args.func(args)
