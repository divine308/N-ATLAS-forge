import csv
import io
import json
from collections import Counter
from datetime import date, datetime
from typing import Any


class DatasetValidationError(Exception):
    pass


SUPPORTED_FORMATS = {
    ".json": "json",
    ".jsonl": "jsonl",
    ".csv": "csv",
}


def parse_dataset(
    content: bytes,
    filename: str,
) -> tuple[str, list[dict[str, Any]]]:

    name = filename.lower().strip()

    format_name = None

    for extension, detected_format in SUPPORTED_FORMATS.items():
        if name.endswith(extension):
            format_name = detected_format
            break

    if not format_name:
        raise DatasetValidationError(
            "Unsupported dataset format. Use CSV, JSON or JSONL."
        )

    if format_name == "jsonl":

        records = []

        text = content.decode("utf-8-sig")

        for line_number, line in enumerate(
            text.splitlines(),
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(
                    f"Invalid JSONL at line {line_number}: {exc}"
                )

            if not isinstance(item, dict):
                raise DatasetValidationError(
                    f"Line {line_number} must contain a JSON object."
                )

            records.append(item)

        return format_name, records

    if format_name == "json":

        try:
            parsed = json.loads(
                content.decode("utf-8-sig")
            )
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(
                f"Invalid JSON: {exc}"
            )

        if isinstance(parsed, dict):
            records = [parsed]

        elif isinstance(parsed, list):
            records = parsed

        else:
            raise DatasetValidationError(
                "JSON must contain an object or an array of objects."
            )

        if not all(
            isinstance(item, dict)
            for item in records
        ):
            raise DatasetValidationError(
                "Every dataset record must be a JSON object."
            )

        return format_name, records

    text = content.decode("utf-8-sig")

    reader = csv.DictReader(
        io.StringIO(text)
    )

    if not reader.fieldnames:
        raise DatasetValidationError(
            "CSV does not contain headers."
        )

    headers = [
        str(header).strip()
        for header in reader.fieldnames
        if header is not None
    ]

    if not headers:
        raise DatasetValidationError(
            "CSV does not contain usable headers."
        )

    records = []

    for row_number, row in enumerate(
        reader,
        start=2,
    ):
        normalized = {}

        for key, value in row.items():

            if key is None:
                continue

            normalized[str(key).strip()] = (
                value
            )

        records.append(normalized)

    return format_name, records


def infer_value_type(
    value: Any,
) -> str:

    if value is None:
        return "null"

    if isinstance(value, bool):
        return "boolean"

    if isinstance(value, int) and not isinstance(
        value,
        bool,
    ):
        return "integer"

    if isinstance(value, float):
        return "number"

    if isinstance(value, (dict, list)):
        return "object" if isinstance(
            value,
            dict,
        ) else "array"

    if isinstance(value, str):

        stripped = value.strip()

        if not stripped:
            return "string"

        try:
            datetime.fromisoformat(
                stripped.replace(
                    "Z",
                    "+00:00",
                )
            )

            return "datetime"

        except ValueError:
            pass

        if stripped.lower() in {
            "true",
            "false",
        }:
            return "boolean"

        try:
            int(stripped)
            return "integer"
        except ValueError:
            pass

        try:
            float(stripped)
            return "number"
        except ValueError:
            pass

        return "string"

    return "unknown"


def infer_schema(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:

    field_types: dict[
        str,
        Counter,
    ] = {}

    field_presence: dict[
        str,
        int,
    ] = {}

    total = len(records)

    for record in records:

        for key, value in record.items():

            key = str(key)

            if key not in field_types:
                field_types[key] = Counter()

            field_types[key][
                infer_value_type(value)
            ] += 1

            field_presence[key] = (
                field_presence.get(
                    key,
                    0,
                )
                + 1
            )

    schema = {}

    for field, types in field_types.items():

        ordered = types.most_common()

        detected_type = (
            ordered[0][0]
            if ordered
            else "unknown"
        )

        if len(ordered) > 1:
            non_null_types = [
                item
                for item in ordered
                if item[0] != "null"
            ]

            if non_null_types:
                detected_type = (
                    non_null_types[0][0]
                )

        schema[field] = {
            "type": detected_type,
            "nullable": "null" in types,
            "present": field_presence.get(
                field,
                0,
            ),
            "missing": max(
                total
                - field_presence.get(
                    field,
                    0,
                ),
                0,
            ),
            "types": dict(types),
        }

    return schema


def estimate_size_bytes(
    records: list[dict[str, Any]],
    format_name: str,
) -> int:

    if format_name == "jsonl":

        text = "\n".join(
            json.dumps(
                record,
                ensure_ascii=False,
            )
            for record in records
        )

    elif format_name == "json":

        text = json.dumps(
            records,
            ensure_ascii=False,
            indent=2,
        )

    else:

        if not records:
            return 0

        fields = list(records[0].keys())

        output = io.StringIO()

        writer = csv.DictWriter(
            output,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(records)

        text = output.getvalue()

    return len(
        text.encode("utf-8")
    )


def build_validation_report(
    records: list[dict[str, Any]],
) -> dict:

    field_counts: dict[str, int] = {}

    empty_fields = []

    duplicate_indexes = []

    seen = set()

    missing_input = []

    missing_expected = []

    languages: dict[str, int] = {}

    categories: dict[str, int] = {}

    for index, record in enumerate(
        records
    ):

        serialized = json.dumps(
            record,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

        if serialized in seen:
            duplicate_indexes.append(
                index
            )

        seen.add(serialized)

        for field in record.keys():

            field_counts[field] = (
                field_counts.get(
                    field,
                    0,
                )
                + 1
            )

        input_value = (
            record.get("input")
            or record.get("prompt")
            or record.get("question")
        )

        expected_value = (
            record.get("expected")
            or record.get("answer")
            or record.get(
                "expected_answer"
            )
        )

        if not input_value:
            missing_input.append(index)

        if (
            "expected" in record
            or "answer" in record
            or "expected_answer" in record
        ):

            if not expected_value:
                missing_expected.append(
                    index
                )

        language = record.get(
            "language",
            "unknown",
        )

        if language is None or language == "":
            language = "unknown"

        language = str(language)

        languages[language] = (
            languages.get(
                language,
                0,
            )
            + 1
        )

        category = record.get(
            "category",
            "uncategorized",
        )

        if category is None or category == "":
            category = "uncategorized"

        category = str(category)

        categories[category] = (
            categories.get(
                category,
                0,
            )
            + 1
        )

        for key, value in record.items():

            if value is None:

                empty_fields.append(
                    {
                        "index": index,
                        "field": key,
                    }
                )

            elif (
                isinstance(
                    value,
                    str,
                )
                and not value.strip()
            ):

                empty_fields.append(
                    {
                        "index": index,
                        "field": key,
                    }
                )

    total = len(records)

    schema = infer_schema(records)

    return {
        "record_count": total,
        "field_counts": field_counts,
        "field_count": len(schema),
        "schema": schema,
        "duplicate_count": len(
            duplicate_indexes
        ),
        "duplicate_indexes": (
            duplicate_indexes[:100]
        ),
        "missing_input_count": len(
            missing_input
        ),
        "missing_input_indexes": (
            missing_input[:100]
        ),
        "missing_expected_count": len(
            missing_expected
        ),
        "missing_expected_indexes": (
            missing_expected[:100]
        ),
        "empty_field_count": len(
            empty_fields
        ),
        "empty_fields": empty_fields[:100],
        "language_distribution": languages,
        "category_distribution": categories,
    }


def validate_records(
    records: list[dict[str, Any]],
) -> dict:

    return build_validation_report(
        records
    )


def serialize_records(
    records: list[dict[str, Any]],
    format_name: str,
) -> bytes:

    if format_name == "json":

        return json.dumps(
            records,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

    if format_name == "jsonl":

        return (
            "\n".join(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                for record in records
            )
            + ("\n" if records else "")
        ).encode("utf-8")

    if format_name == "csv":

        if not records:
            return b""

        fields = []

        for record in records:
            for field in record.keys():
                if field not in fields:
                    fields.append(field)

        output = io.StringIO()

        writer = csv.DictWriter(
            output,
            fieldnames=fields,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(records)

        return output.getvalue().encode(
            "utf-8"
        )

    raise DatasetValidationError(
        f"Unsupported dataset format: {format_name}"
    )


def get_dataset_extension(
    format_name: str,
) -> str:

    return {
        "json": ".json",
        "jsonl": ".jsonl",
        "csv": ".csv",
    }.get(
        format_name,
        ".json",
    )