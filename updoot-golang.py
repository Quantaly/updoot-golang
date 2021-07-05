#!/bin/python3

import os
import shutil
import tempfile
import sys
import requests
import platform
import hashlib
import argparse
import re

# TODO: detect from environment or `go env GOROOT` or shutil.which() if set to None
GOROOT = '/usr/local/go'

GOWEBSITE = 'https://golang.org'

# dicts map from Python names to Go names
# TODO: support more OS's/arch's

OS_DICT = {
    'Linux': 'linux',
}

ARCH_DICT = {
    'x86_64': 'amd64',
    'aarch64': 'arm64',
}

INT_REGEX = re.compile(r'\d+')


def detect_platform():
    def platform_unsupported():
        print('this OS and/or architecture is not supported by updoot-golang :(')
        print('try looking at OS_DICT and ARCH_DICT')
        print('see if you can add your situation to the relevant dict(s)')
        print('though if it\'s something weird they don\'t build Go for, you\'ll just get a ~*~different error~*~')
        print('if you fix this for yourself, plz send me a PR (https://github.com/Quantaly/updoot-golang/)')
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

    if not unstable:
        versions = list(filter(lambda v: v['stable'], versions))
    return versions

# True if b is more recent than a


def cmp_versions(a, b):
    def replace_none_with_zero_tuple(value):
        if value is None:
            return (0,)
        return value

    a_major = replace_none_with_zero_tuple(INT_REGEX.search(a))
    b_major = replace_none_with_zero_tuple(INT_REGEX.search(b))
    a_major_int, b_major_int = int(a_major[0]), int(b_major[0])
    if a_major_int != b_major_int:
        return b_major_int > a_major_int

    a_minor = replace_none_with_zero_tuple(INT_REGEX.search(a, a_major.end()))
    b_minor = replace_none_with_zero_tuple(INT_REGEX.search(b, b_major.end()))
    a_minor_int, b_minor_int = int(a_minor[0]), int(b_minor[0])
    if a_minor_int != b_minor_int:
        return b_minor_int > a_minor_int

    a_beta, a_rc = 'beta' in a, 'rc' in a
    b_beta, b_rc = 'beta' in b, 'rc' in b

    if a_beta == b_beta and a_rc == b_rc:
        a_patch = replace_none_with_zero_tuple(
            INT_REGEX.search(a, a_minor.end()))
        b_patch = replace_none_with_zero_tuple(
            INT_REGEX.search(b, b_minor.end()))
        if b_patch is None:
            b_patch = (0,)
        a_patch_int, b_patch_int = int(a_patch[0]), int(b_patch[0])
        return b_patch_int > a_patch_int
    else:
        # is a release and b prerelease?
        if not (a_beta or a_rc) and (b_beta or b_rc):
            return False
        # is b release and a prerelease?
        elif not (b_beta or b_rc) and (a_beta or a_rc):
            return True
        # is a release candidate and b beta?
        elif a_rc and b_beta:
            return False
        # is b release candidate and a beta?
        elif b_rc and a_beta:
            return True
        # either the versions are the same or the version strings are very weird
        return False


def find_latest_version(versions):
    latest = versions[0]
    for version in versions[1:]:
        if cmp_versions(latest['version'], version['version']):
            latest = version
    return latest


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
        shutil.move(os.path.join(
            olddir.name, os.path.basename(GOROOT)), GOROOT)
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


def install_version(version):
    opsys, arch = detect_platform()
    for file in version['files']:
        if file['kind'] == 'archive' and file['os'] == opsys and file['arch'] == arch:
            install_file(file)
            break
    else:
        print(
            'No suitable build of {} was found for {}/{}'.format(version['version'], opsys, arch))
        sys.exit(1)


# command entrypoints

def install_latest(args):
    versions = get_versions(args.all, args.unstable)
    install_version(find_latest_version(versions))


def install(args):
    target = args.version
    if not target.startswith('go'):
        target = 'go' + target

    versions = get_versions(False, False)
    for version in versions:
        if version['version'] == target:
            install_version(version)
            break
    else:
        versions = get_versions(True, True)
        for version in versions:
            if version['version'] == target:
                install_version(version)
                break
        else:
            print('Version {} was not found.'.format(target))
            sys.exit(1)


def list_versions(args):
    versions = get_versions(args.all, args.unstable)
    for version in versions:
        print(version['version'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manages a Go installation.')
    parser.set_defaults(func=install_latest, all=False, unstable=False)
    parser.add_argument('-u', '--unstable', action='store_true',
                        help='install the latest unstable version')
    subparsers = parser.add_subparsers()

    parser_install_latest = subparsers.add_parser(
        'install-latest', help='Install the latest stable version (invoked by default)')
    # already the global default, but meh whatever
    parser_install_latest.set_defaults(func=install_latest)
    parser_install_latest.add_argument('-u', '--unstable', action='store_true',
                                       help='install the latest version, which may be unstable')

    parser_install = subparsers.add_parser(
        'install', help='Install a specified version')
    parser_install.add_argument('version')
    parser_install.set_defaults(func=install)

    parser_list = subparsers.add_parser(
        'list', help='List supported stable versions')
    parser_list.set_defaults(func=list_versions)
    parser_list.add_argument('-a', '--all', action='store_true',
                             help='list all stable versions')
    parser_list.add_argument('-u', '--unstable', action='store_true',
                             help='list all stable and unstable versions')

    args = parser.parse_args()
    args.func(args)
