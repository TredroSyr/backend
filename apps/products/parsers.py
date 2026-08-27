# apps/products/parsers.py
import json
from rest_framework.parsers import MultiPartParser, DataAndFiles
from rest_framework.exceptions import ParseError


class NestedJSONMultiPartParser(MultiPartParser):
    """
    Expects multipart/form-data with:
      - 'data': JSON string matching ProductWriteSerializer's shape
      - file parts referenced from within 'data' via '_file_ref'
        (used for images[i].image)
    """

    def parse(self, stream, media_type=None, parser_context=None):
        result = super().parse(stream, media_type, parser_context)

        raw = result.data.get("data")
        if raw is None:
            raise ParseError("Missing required 'data' field with JSON payload.")

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ParseError(f"'data' field is not valid JSON: {exc}")

        if not isinstance(payload, dict):
            raise ParseError("'data' field must decode to a JSON object.")

        for image in payload.get("images", []):
            ref = image.pop("_file_ref", None)
            if ref is not None:
                uploaded = result.files.get(ref)
                if uploaded is None:
                    raise ParseError(f"Referenced file '{ref}' was not uploaded.")
                image["image"] = uploaded

        return DataAndFiles(payload, result.files)