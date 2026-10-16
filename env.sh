# Source this file before running Maelstrom:   source ~/TF/env.sh
#
# Java 17 and gnuplot were installed in user space (~/.local/opt) because the
# machine has no passwordless sudo. If you install them system-wide instead
#   sudo apt install openjdk-17-jre-headless gnuplot-nox
# this file is no longer needed.

export JAVA_HOME="$HOME/.local/opt/jdk-17.0.20.1+1-jre"
export PATH="$JAVA_HOME/bin:$HOME/.local/bin:$PATH"
