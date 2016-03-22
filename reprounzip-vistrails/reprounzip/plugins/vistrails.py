# Copyright (C) 2014-2017 New York University
# This file is part of ReproZip which is released under the Revised BSD License
# See file LICENSE for full license details.

"""VisTrails runner for reprounzip.

This file provides the reprounzip plugin that builds a VisTrails pipeline
alongside an unpacked experiment. Although you don't need VisTrails to generate
the .vt file, you will need it if you want to run it.

See http://www.vistrails.org/
"""

from __future__ import division, print_function, unicode_literals

if __name__ == '__main__':  # noqa
    from reprounzip.plugins.vistrails import run_from_vistrails
    run_from_vistrails()

import argparse
from datetime import datetime
import itertools
import logging
import os
from rpaths import Path
import subprocess
import sys
import zipfile

from reprounzip.common import load_config, setup_logging, record_usage
from reprounzip import signals
from reprounzip.unpackers.common import shell_escape
from reprounzip.utils import iteritems


__version__ = '1.0.5'


logger = logging.getLogger('reprounzip.vistrails')


def escape_xml(s):
    """Escapes for XML.
    """
    return ("%s" % s).replace('&', '&amp;').replace('"', '&quot;')


class IdScope(object):
    def __init__(self):
        self._ids = {'add': 0,
                     'module': 0,
                     'location': 0,
                     'annotation': 0,
                     'function': 0,
                     'parameter': 0,
                     'connection': 0,
                     'port': 0,
                     'portspec': 0,
                     'portspecitem': 0}

    def _add(type_):
        def getter(self):
            i = self._ids[type_]
            self._ids[type_] += 1
            return i
        return getter

    add = _add('add')
    module = _add('module')
    location = _add('location')
    annotation = _add('annotation')
    function = _add('function')
    parameter = _add('parameter')
    connection = _add('connection')
    port = _add('port')
    portspec = _add('portspec')
    portspecitem = _add('portspecitem')

    del _add


def split_sig(sig):
    pkg, name = sig.rsplit(':', 1)
    return name, pkg


class Workflow(object):
    def __init__(self, file_, ids):
        self._file = file_
        self._ids = ids
        self._mod_y = 0

        file_.write('<vistrail id="" name="" version="1.0.4" xmlns:xsi="http:'
                    '//www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation'
                    '="http://www.vistrails.org/vistrail.xsd">\n'
                    '<!-- Generated by reprounzip-vistrails {version} -->\n'
                    '  <action date="{date}" id="1" prevId="0" session="0" '
                    'user="ReproUnzip">\n'.format(
                        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        version=__version__))

    def close(self):
        self._file.write(
            '  </action>\n'
            '</vistrail>\n')

    def add_module(self, sig, version, desc=None):
        mod_id = self._ids.module()
        name, pkg = split_sig(sig)
        self._file.write(
            '    <add id="{add_id}" objectId="{mod_id}" parentObjId="" '
            'parentObjType="" what="module">\n'
            '      <module cache="1" id="{mod_id}" name="{mod_name}" namespace'
            '="" package="{mod_pkg}" version="{version}" />\n'
            '    </add>\n'.format(
                add_id=self._ids.add(), mod_id=mod_id,
                mod_name=name, mod_pkg=pkg, version=version))
        self._file.write(
            '    <add id="{add_id}" objectId="{loc_id}" parentObjId="{mod_id}'
            '" parentObjType="module" what="location">\n'
            '      <location id="{loc_id}" x="0.0" y="{y}" />\n'
            '    </add>\n'.format(
                add_id=self._ids.add(), mod_id=mod_id,
                loc_id=self._ids.location(), y=self._mod_y))
        if desc is not None:
            self._file.write(
                '    <add id="{add_id}" objectId="{ann_id}" parentObjId="'
                '{mod_id}" parentObjType="module" what="annotation">\n'
                '      <annotation id="{ann_id}" key="__desc__" value="{text}"'
                ' />\n'
                '    </add>\n'.format(
                    add_id=self._ids.add(), mod_id=mod_id,
                    ann_id=self._ids.annotation(), text=escape_xml(desc)))
        self._mod_y -= 100
        return mod_id

    def add_function(self, mod_id, name, param_values):
        func_id = self._ids.function()
        self._file.write(
            '    <add id="{add_id}" objectId="{func_id}" parentObjId="'
            '{mod_id}" parentObjType="module" what="function">\n'
            '      <function id="{func_id}" name="{name}" pos="0" />\n'
            '    </add>\n'.format(
                add_id=self._ids.add(), mod_id=mod_id, func_id=func_id,
                name=name))

        for i, (sig, val) in enumerate(param_values):
            self._file.write(
                '    <add id="{add_id}" objectId="{param_id}" parentObjId="'
                '{func_id}" parentObjType="function" what="parameter">\n'
                '      <parameter alias="" id="{param_id}" name="&lt;no '
                'description&gt;" pos="{pos}" type="{type}" val="{val}" />\n'
                '    </add>\n'.format(
                    add_id=self._ids.add(), param_id=self._ids.parameter(),
                    func_id=func_id, pos=i, type=sig, val=escape_xml(val)))

    def connect(self, from_id, from_sig, from_port, to_id, to_sig, to_port):
        self._file.write(
            '    <add id="{add1_id}" objectId="{conn_id}" parentObjId="" '
            'parentObjType="" what="connection">\n'
            '      <connection id="{conn_id}" />\n'
            '    </add>\n'
            '    <add id="{add2_id}" objectId="{port1_id}" parentObjId="'
            '{conn_id}" parentObjType="connection" what="port">\n'
            '      <port id="{port1_id}" moduleId="{from_id}" moduleName="'
            '{from_mod}" name="{from_port}" signature="({from_sig})" type="'
            'source" />\n'
            '    </add>\n'
            '    <add id="{add3_id}" objectId="{port2_id}" parentObjId="'
            '{conn_id}" parentObjType="connection" what="port">\n'
            '      <port id="{port2_id}" moduleId="{to_id}" moduleName="'
            '{to_mod}" name="{to_port}" signature="({to_sig})" type="'
            'destination" />\n'
            '    </add>\n'.format(
                add1_id=self._ids.add(), add2_id=self._ids.add(),
                add3_id=self._ids.add(), conn_id=self._ids.connection(),
                port1_id=self._ids.port(), from_id=from_id, from_sig=from_sig,
                from_mod=split_sig(from_sig)[0], from_port=from_port,
                port2_id=self._ids.port(), to_id=to_id, to_sig=to_sig,
                to_mod=split_sig(to_sig)[0], to_port=to_port
            ))

    def add_port_spec(self, mod_id, name, type_, sigs, optional=True):
        self._file.write(
            '    <add id="{add_id}" objectId="{ps_id}" parentObjId="{mod_id}" '
            'parentObjType="module" what="portSpec">\n'
            '      <portSpec depth="0" id="{ps_id}" maxConns="1" minConns="0" '
            'name="{name}" optional="{opt}" sortKey="0" type="{type}'
            '">\n'.format(
                add_id=self._ids.add(), ps_id=self._ids.portspec(),
                mod_id=mod_id, name=escape_xml(name), type=type_,
                opt='1' if optional else '0'))
        for i, (pkg, mod) in enumerate(sigs):
            self._file.write(
                '        <portSpecItem default="" entryType="" id="{psi_id}" '
                'label="" module="{mod}" namespace="" package="{pkg}" pos="'
                '{pos}" values="" />\n'.format(
                    psi_id=self._ids.portspecitem(), mod=mod, pkg=pkg,
                    pos=i))
        self._file.write(
            '      </portSpec>\n'
            '    </add>\n')


directory_sig = 'org.vistrails.vistrails.basic:Directory'
file_pkg_mod = 'org.vistrails.vistrails.basic', 'File'
integer_sig = 'org.vistrails.vistrails.basic:Integer'
string_sig = 'org.vistrails.vistrails.basic:String'
rpz_id = 'io.github.vida-nyu.reprozip.reprounzip'
rpz_version = '0.1'
experiment_sig = '%s:Directory' % rpz_id


def do_vistrails(target, pack=None, **kwargs):
    """Create a VisTrails workflow that runs the experiment.

    This is called from signals after an experiment has been setup by any
    unpacker.
    """
    record_usage(do_vistrails=True)

    config = load_config(target / 'config.yml', canonical=True)

    # Writes VisTrails workflow
    bundle = target / 'vistrails.vt'
    logger.info("Writing VisTrails workflow %s...", bundle)
    vtdir = Path.tempdir(prefix='reprounzip_vistrails_')
    ids = IdScope()
    try:
        with vtdir.open('w', 'vistrail',
                        encoding='utf-8', newline='\n') as fp:
            wf = Workflow(fp, ids)

            # Directory module, refering to this directory
            d = wf.add_module('%s:Directory' % rpz_id, rpz_version)
            wf.add_function(d, 'directory',
                            [(directory_sig, str(target.resolve()))])

            connect_from = d

            for i, run in enumerate(config.runs):
                inputs = sorted(n for n, f in iteritems(config.inputs_outputs)
                                if i in f.read_runs)
                outputs = sorted(n for n, f in iteritems(config.inputs_outputs)
                                 if i in f.write_runs)
                ports = itertools.chain((('input', p) for p in inputs),
                                        (('output', p) for p in outputs))

                # Run module
                r = wf.add_module('%s:Run' % rpz_id, rpz_version,
                                  desc=run.get('id', 'run%d' % i))
                wf.add_function(r, 'cmdline', [
                                (string_sig,
                                 ' '.join(shell_escape(arg)
                                          for arg in run['argv']))])
                wf.add_function(r, 'run_number', [(integer_sig, i)])

                # Port specs for input/output files
                for type_, name in ports:
                    wf.add_port_spec(r, name, type_, [file_pkg_mod])

                # Draw connection
                wf.connect(connect_from, experiment_sig, 'experiment',
                           r, experiment_sig, 'experiment')
                connect_from = r

            wf.close()

        with bundle.open('wb') as fp:
            z = zipfile.ZipFile(fp, 'w')
            with vtdir.in_dir():
                for path in Path('.').recursedir():
                    z.write(str(path))
            z.close()
    finally:
        vtdir.rmtree()


def setup_vistrails():
    """Setup the plugin.
    """
    signals.post_setup.subscribe(do_vistrails)


def run_from_vistrails():
    setup_logging('REPROUNZIP-VISTRAILS', logging.INFO)

    cli_version = 1
    if len(sys.argv) > 1:
        try:
            cli_version = int(sys.argv[1])
        except ValueError:
            logger.info("Compatibility mode: reprounzip-vistrails didn't get "
                        "a version number")
    if cli_version != 1:
        logger.critical("Unknown interface version %d; you are probably "
                        "using a version of reprounzip-vistrails too old for "
                        "your VisTrails package. Consider upgrading.",
                        cli_version)
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument('unpacker')
    parser.add_argument('directory')
    parser.add_argument('run')
    parser.add_argument('--input-file', action='append', default=[])
    parser.add_argument('--output-file', action='append', default=[])
    parser.add_argument('--cmdline', action='store')

    args = parser.parse_args(sys.argv[2:])

    config = load_config(Path(args.directory) / 'config.yml', canonical=True)

    python = sys.executable
    rpuz = [python, '-c', 'from reprounzip.main import main; main()',
            args.unpacker]

    os.environ['REPROUNZIP_NON_INTERACTIVE'] = 'y'

    def cmd(lst, add=None):
        if add:
            logger.info("cmd: %s %s", ' '.join(rpuz + lst), add)
            string = ' '.join(shell_escape(a) for a in (rpuz + lst))
            string += ' ' + add
            subprocess.check_call(string, shell=True,
                                  cwd=args.directory)
        else:
            logger.info("cmd: %s", ' '.join(rpuz + lst))
            subprocess.check_call(rpuz + lst,
                                  cwd=args.directory)

    logger.info("reprounzip-vistrails calling reprounzip; dir=%s",
                args.directory)

    # Parses input files from the command-line
    upload_command = []
    seen_input_names = set()
    for input_file in args.input_file:
        input_name, filename = input_file.split(':', 1)
        upload_command.append('%s:%s' % (filename, input_name))
        seen_input_names.add(input_name)

    # Resets the input files that are used by this run and were not given
    for name, f in iteritems(config.inputs_outputs):
        if name not in seen_input_names and int(args.run) in f.read_runs:
            upload_command.append(':%s' % name)

    # Runs the command
    cmd(['upload', '.'] + upload_command)

    # Runs the experiment
    if args.cmdline:
        cmd(['run', '.', args.run, '--cmdline'], add=args.cmdline)
    else:
        cmd(['run', '.', args.run])

    # Gets output files
    for output_file in args.output_file:
        output_name, filename = output_file.split(':', 1)
        cmd(['download', '.',
             '%s:%s' % (output_name, filename)])
