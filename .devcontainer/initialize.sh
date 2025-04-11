base_dir=$(dirname $(dirname $(readlink -f $0)))
${base_dir}/docker/create_env.sh
