import os
import re
import shutil
import subprocess


toplevel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


re_setup = re.compile(r'setup\(')
re_version = re.compile(r'(?<=\bversion=[\'"])([0-9a-zA-Z._+-]+)')


def update_version(gitversion, foundversion):
    return gitversion


if __name__ == '__main__':
    # Get version from git describe
    version = subprocess.check_output(['git', 'describe', '--always'],
                                      cwd=toplevel).strip()

    dest = os.path.join(toplevel, 'dist')

    if not os.path.exists(dest):
        os.mkdir(dest)

    for project in ('reprozip', 'reprounzip', 'reprounzip-vagrant'):
        pdir = os.path.join(toplevel, project)
        setup_py = os.path.join(pdir, 'setup.py')

        # Update setup.py file
        with open(setup_py, 'rb') as fp:
            lines = fp.readlines()

        i = 0
        setup_found = False
        while i < len(lines):
            line = lines[i]
            if not setup_found and re_setup.search(line):
                setup_found = True
            if setup_found:
                m = re_version.search(line)
                if m is not None:
                    version = update_version(version, m.group(1))
                    lines[i] = re_version.sub(version, line)
                    break
            i += 1

        with open(setup_py, 'wb') as fp:
            for line in lines:
                fp.write(line)

        # Run sdist
        subprocess.check_call(['python', setup_py, 'sdist'])

        # Move output to top-level dist/
        for f in os.listdir(os.path.join(pdir, 'dist')):
            shutil.copyfile(os.path.join(pdir, 'dist', f),
                            os.path.join(dest, f))
