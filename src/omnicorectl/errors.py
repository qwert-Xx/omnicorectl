"""Stable errors shared by the protocol and CLI layers.

协议层与 CLI 层共享的稳定错误类型。
"""


class OmnicoreError(Exception):
    """Base class for expected omnicorectl failures. / 预期错误的基类。"""


class ConfigurationError(OmnicoreError):
    """The command has missing or invalid local configuration. / 本地配置缺失或无效。"""


class NetworkError(OmnicoreError):
    """The controller could not be reached in time. / 无法及时连接控制器。"""


class AuthenticationError(OmnicoreError):
    """The controller rejected the supplied credentials. / 控制器拒绝了所提供的凭据。"""


class AuthorizationError(OmnicoreError):
    """The user lacks the required controller grant. / 已认证用户缺少所需控制器权限。"""


class ProtocolError(OmnicoreError):
    """The controller returned an unexpected RWS payload. / 控制器返回了异常 RWS 数据。"""


class RapidBuildError(OmnicoreError):
    """A RAPID edit produced controller build errors. / RAPID 编辑产生了控制器构建错误。"""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: tuple[str, ...],
        rolled_back: bool,
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics
        self.rolled_back = rolled_back


class RwsHttpError(OmnicoreError):
    """RWS returned an unsuccessful HTTP response. / RWS 返回了失败的 HTTP 响应。"""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        controller_code: str = "",
        controller_message: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.controller_code = controller_code
        self.controller_message = controller_message
