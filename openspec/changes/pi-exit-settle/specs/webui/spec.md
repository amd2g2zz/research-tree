## ADDED Requirements

### Requirement: runPi settles at the pi process's own exit

runPi SHALL 在 pi 本体 exit 时结算（成功取 stdout / 失败取退出码）——扩展派生的孙进程继承 stdio SHALL NOT 阻止结算（close 等待管道写者永不触发的场景）；超时 SHALL SIGKILL 整个进程组并给出含重试指引的 typed 错误。

#### Scenario: grandchild holding stdio
- **WHEN** the pi process prints its answer, spawns a long-lived grandchild inheriting stdio, and exits
- **THEN** runPi settles with the answer quickly (not at the grandchild's eventual death)

#### Scenario: group kill on timeout
- **WHEN** the pi process hangs past the timeout
- **THEN** the whole process group is SIGKILLed and a typed error with retry guidance lands
