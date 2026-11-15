from dify_plugin import ToolProvider


class EkpsCleanChunkerProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, object]) -> None:
        """不需要任何凭据：全部在插件内处理，不调用外部服务。"""
        return None
