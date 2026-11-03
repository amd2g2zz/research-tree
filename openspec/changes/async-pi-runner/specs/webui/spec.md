## ADDED Requirements

### Requirement: pi calls never block the event loop

所有 pi 会话调用 SHALL 异步执行（事件循环保持畅通）——慢模型调用在飞期间，其它 HTTP/WS 请求 SHALL 正常响应（<1s）。

#### Scenario: in-flight turn does not block reads
- **WHEN** a chat.turn with a 3s runner is in flight and a REST read arrives
- **THEN** the REST read completes in under 1s while the turn continues

### Requirement: hung pi processes are killed with a typed error

pi 调用 SHALL 有硬超时：挂起进程被 kill 并以 typed 错误失败关闭（PiRunError）——SHALL NOT 永久冻结 server。

#### Scenario: hung process killed
- **WHEN** the pi process exceeds the timeout
- **THEN** runPi rejects with a typed error and the server stays alive
