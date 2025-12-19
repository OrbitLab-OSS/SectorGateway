shell_source(name="build-script", source="build.sh")

run_shell_command(
    name="build",
    command="CHROOT={chroot} bash ./build.sh",
    execution_dependencies=[":build-script", "sgwtool:sgwtool"],
)
