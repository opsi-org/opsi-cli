import orjson
from opsicommon.logging import get_logger

from opsicli.io import deprecation_warning, output_file_is_stdout, read_input, write_output
from opsicli.opsiservice import get_service_connection

__version__ = "0.1.0"

logger = get_logger("opsicli")


def execute_rpc_call(method: str, params: list[str] | None = None, timeout: float | None = None) -> None:
	if params:
		logger.debug("Raw parameters: %s", params)
		params = list(params)
		for idx, param in enumerate(params):
			try:
				params[idx] = orjson.loads(param)
			except orjson.JSONDecodeError:
				params[idx] = orjson.loads(f'"{param}"')
	else:
		params = []

	inp_param = read_input()
	if inp_param is not None:
		# TODO: Handle params depending on method parameters
		params.append(inp_param)

	default_output_format = "pretty-json" if output_file_is_stdout() else "json"

	client = get_service_connection()
	method_interface = client.get_jsonrpc_method(method)
	if method_interface.get("deprecated"):
		deprecation_warning(f"Method {method!r} is deprecated and may not be supported in future versions.")

	logger.info("Calling method %s with params %s", method, params)
	data = client.jsonrpc(method, params, create_objects=False, read_timeout=float(timeout) if timeout else None)
	write_output(data, default_output_format=default_output_format)
