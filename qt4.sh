
#!/usr/local/bin/bash
# This hook is run after a new virtualenv is activated.

#set -e # abort after any errors
#set -u # exit after accessing an undefined variable

# version-test.sh
echo $BASH_VERSION

libs=(PyQt4 sip.so sipconfig.py)

python_version=python$(python -c "import sys; print (str(sys.version_info[0])+'.'+str(sys.version_info[1]))")
var=( $(which -a ${python_version}) )

if [ ${#var[@]} -lt 2 ]; then
    echo "could not find system install of ${python_version}: unable to link PyQt components" >&2
else
    get_python_lib_cmd="from distutils.sysconfig import get_python_lib; print (get_python_lib())"
    lib_virtualenv_path=$(${var[0]} -c "${get_python_lib_cmd}")
    lib_system_path=$(${var[-1]} -c "${get_python_lib_cmd}")
    for lib in ${libs[@]}
    do
        if [ ! -e "${lib_virtualenv_path}/${lib}" ]; then
            ln -s "${lib_system_path}/${lib}" "${lib_virtualenv_path}/${lib}"
        fi
    done
fi