# !/bin/bash
# 装一下docker-compose
# This script should be run via curl:
#   sh -c "$(curl -fsSL https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"
#   sh -c "$(curl -fsSL https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"
# or via wget:
#   sh -c "$(wget -qO- https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"
#   sh -c "$(wget -qO- https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"
# or via fetch:
#   sh -c "$(fetch -o - https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"
#   sh -c "$(fetch -o - https://ghproxy.com/https://raw.githubusercontent.com/Sowevo/my_script/main/shell/install_docker_compose.sh)"

if ! [ $(command -v docker-compose) ]; then
    # Get latest docker compose version number
    get_latest_release() {
        curl --silent "https://api.github.com/repos/docker/compose/releases/latest" |
        grep '"tag_name":' |
        sed -E 's/.*"([^"]+)".*/\1/'
    }

    # Install Docker compose
    echo "Installing Docker Compose..."
    curl -L https://github.com/docker/compose/releases/download/`get_latest_release`/docker-compose-`uname -s`-`uname -m` -o /usr/bin/docker-compose
    chmod +x /usr/bin/docker-compose
    if [ $? -eq 0 ]; then
        echo "Docker Compose installed successfully."
        docker-compose -v
    else
        echo "Failed to install Docker Compose."
    fi
else
    echo "Docker Compose is already installed."
fi
