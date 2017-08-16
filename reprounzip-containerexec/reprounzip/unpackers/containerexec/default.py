# Copyright (C) 2014-2017 New York University
# This file is part of ReproZip which is released under the Revised BSD License
# See file LICENSE for full license details.

"""Containerexec plugin for reprounzip."""

# prepare for Python 3
from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import logging
import os
import signal
import socket
from rpaths import Path
import sys

from reprounzip import signals
from reprounzip.common import load_config as load_config_file
from reprounzip.unpackers.common import target_must_exist, shell_escape, \
    get_runs, add_environment_options, fixup_environment, metadata_read, \
    metadata_write, metadata_update_run
from reprounzip.unpackers.common.x11 import X11Handler, LocalForwarder
from reprounzip.unpackers.default import chroot_create, chroot_destroy_dir, \
    test_linux_same_arch
from reprounzip.unpackers.containerexec import baseexecutor, BenchExecException, \
    containerexecutor
from reprounzip.unpackers.containerexec import util as containerexec_util
from reprounzip.utils import unicode_, iteritems, stderr

CONFIGURE_REPROUNZIP_CONTAINER = True

@target_must_exist
def containerexec_upload(args):
    """Replaces an input file in the sandbox.
    """
    logging.info('containerexec_upload')


@target_must_exist
def containerexec_run(args):
    """Runs the experiment in an isolated environment.
    """
    if args is None:
        args = sys.args

    #logging.info('Received arguments: %s', args)

    target = Path(args.target[0])
    unpacked_info = metadata_read(target, 'chroot')
    cmdline = args.cmdline

    # Loads config
    config = load_config_file(target / 'config.yml', True)
    runs = config.runs

    selected_runs = get_runs(runs, args.run, cmdline)

    # X11 handler
    x11 = X11Handler(args.x11, ('local', socket.gethostname()),
                     args.x11_display)

    cmds = []
    uid = 0
    gid = 0
    for run_number in selected_runs:
        run = runs[run_number]
        #cmd = 'cd %s; ' % (shell_escape(run['workingdir']))
        #workingDir = shell_escape(run['workingdir'])
        cmd = 'cd %s && ' % shell_escape(run['workingdir'])
        cmd += '/usr/bin/env -i '
        environ = x11.fix_env(run['environ'])
        environ = fixup_environment(environ, args)
        cmd += ' '.join('%s=%s' % (shell_escape(k), shell_escape(v))
                        for k, v in iteritems(environ))
        cmd += ' '
        uid = run['uid']
        gid = run['gid']
        # FIXME : Use exec -a or something if binary != argv[0]
        if cmdline is None:
            argv = [run['binary']] + run['argv'][1:]
        else:
            argv = cmdline
        cmd += ' '.join(shell_escape(a) for a in argv)
        cmd = '/bin/sh -c %s' % (shell_escape(cmd))
        cmds.append(cmd)
    cmds = ['/bin/sh -c %s' % (shell_escape(c))
            for c in x11.init_cmds] + cmds
    cmds = ' && '.join(cmds)

    # Starts forwarding
#    forwarders = []
#    for portnum, connector in x11.port_forward:
#        fwd = LocalForwarder(connector, portnum)
#        forwarders.append(fwd)

    executor = containerexecutor.ContainerExecutor(uid=uid, gid=gid)

    # ensure that process gets killed on interrupt/kill signal
    def signal_handler_kill(signum, frame):
        executor.stop()
    signal.signal(signal.SIGTERM, signal_handler_kill)
    signal.signal(signal.SIGINT,  signal_handler_kill)

    # actual run execution
    try:
        signals.pre_run(target=target)
        result = executor.execute_run(cmds, workingDir=target,
                                      setup_reprounzip=CONFIGURE_REPROUNZIP_CONTAINER)
        stderr.write("\n*** Command finished, status: %d\n" % result.value or result.signal)
        signals.post_run(target=target, retcode=result.value)

        # Update input file status
        metadata_update_run(config, unpacked_info, selected_runs)
        metadata_write(target, unpacked_info, 'chroot')

    except (BenchExecException, OSError) as e:
        sys.exit("Cannot execute process: {0}.".format(e))
        # sys.exit("Cannot execute {0}: {1}.".format(containerexec_util.escape_string_shell(args[0]), e))

    return result.signal or result.value


@target_must_exist
def containerexec_download(args):
    """Gets an output file out of the sandbox.
    """
    logging.info('containerexec_download')


def setup(parser, **kwargs):
    """Unpacks the files in a directory and runs the experiment in an isolated environment

    setup           creates the directory (needs the pack filename)
    upload          replaces input files in the directory
                    (without arguments, lists input files)
    run             runs the experiment in the isolated environment
    download        gets output files from the machine
                    (without arguments, lists output files)
    destroy         removes the unpacked directory

    For example:

        $ reprounzip containerexec setup mypackage.rpz path
        $ reprounzip containerexec run path/
        $ reprounzip containerexec download path/ results:/home/user/results.txt
        $ reprounzip containerexec destroy path

    Upload specifications are either:
      :input_id             restores the original input file from the pack
      filename:input_id     replaces the input file with the specified local
                            file

    Download specifications are either:
      output_id:            print the output file to stdout
      output_id:filename    extracts the output file to the corresponding local
                            path
    """

    subparsers = parser.add_subparsers(title="actions",
                                       metavar='', help=argparse.SUPPRESS)

    def add_opt_general(opts):
        opts.add_argument('target', nargs=1, help="Experiment directory")

    # setup/create
    def add_opt_setup(opts):
        opts.add_argument('pack', nargs=1, help="Pack to extract")

    def add_opt_owner(opts):
        opts.add_argument('--preserve-owner', action='store_true',
                          dest='restore_owner', default=None,
                          help="Restore files' owner/group when extracting")
        opts.add_argument('--dont-preserve-owner', action='store_false',
                          dest='restore_owner', default=None,
                          help="Don't restore files' owner/group when "
                               "extracting, use current users")

    # setup
    parser_setup = subparsers.add_parser('setup')
    add_opt_setup(parser_setup)
    add_opt_general(parser_setup)
    add_opt_owner(parser_setup)
    parser_setup.set_defaults(func=chroot_create)

    # upload
    parser_upload = subparsers.add_parser('upload')
    add_opt_general(parser_upload)
    parser_upload.add_argument('file', nargs=argparse.ZERO_OR_MORE,
                               help="<path>:<input_file_name")
    parser_upload.set_defaults(func=containerexec_upload)

    # run
    parser_run = subparsers.add_parser('run')
    add_opt_general(parser_run)
    parser_run.add_argument('run', default=None, nargs=argparse.OPTIONAL)
    parser_run.add_argument('--cmdline', nargs=argparse.REMAINDER,
                            help="Command line to run")
    parser_run.add_argument('--enable-x11', action='store_true', default=False,
                            dest='x11',
                            help="Enable X11 support (needs an X server on "
                                 "the host)")
    parser_run.add_argument('--x11-display', dest='x11_display',
                            help="Display number to use on the experiment "
                                 "side (change the host display with the "
                                 "DISPLAY environment variable)")
    add_environment_options(parser_run)
    parser_run.set_defaults(func=containerexec_run)

    # download
    parser_download = subparsers.add_parser('download')
    add_opt_general(parser_download)
    parser_download.add_argument('file', nargs=argparse.ZERO_OR_MORE,
                                 help="<output_file_name>[:<path>]")
    parser_download.add_argument('--all', action='store_true',
                                 help="Download all output files to the "
                                      "current directory")
    parser_download.set_defaults(func=containerexec_download)

    # destroy
    parser_destroy = subparsers.add_parser('destroy')
    add_opt_general(parser_destroy)
    parser_destroy.set_defaults(func=chroot_destroy_dir)

    return {'test_compatibility': test_linux_same_arch}