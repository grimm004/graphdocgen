from typing import Dict, List, Optional, Set
import sys
import argparse

SCALARS = {"Int", "Float", "String", "Boolean", "ID"}


class GraphQLSchema:
    def __init__(self, name: str = "", schema_type: str = "type") -> None:
        self.name = name
        self.type = schema_type
        self.fields: Dict[str, str] = {}

    def add_field(self, name, dtype):
        self.fields[name] = dtype

    def get_type_id(self, field_name):
        return self.fields[field_name].replace("!", "").replace("[", "").replace("]", "")

    def to_markdown(self, title_prefix: str = "##", scalars: Optional[Set[str]] = None) -> str:
        if scalars is None:
            scalars = SCALARS
        if self.type == "scalar":
            return f"{title_prefix} {self.name}\n\nDatatype class: *{self.type}*"

        table: List[List[str]] = []

        if self.type == "enum":
            headers = ["Values"]
            column_alignments = [":-:"]
            for field in self.fields.keys():
                table.append([f"**`{field}`**"])

        else:
            headers = ["Field", "Description"]
            column_alignments = None
            for field, dtype in self.fields.items():
                if (type_id := self.get_type_id(field)) not in scalars:
                    dtype_md = f"`[<ins>`{type_id}`</ins>](#{type_id.lower()})`".join(dtype.split(type_id))
                    dtype_md = f"{dtype_md.lstrip('`')}" if dtype.startswith(type_id) else f"`{dtype_md}"
                    dtype_md = f"{dtype_md.rstrip('`')}" if dtype.endswith(type_id) else f"{dtype_md}`"
                else:
                    dtype_md = f"`{dtype}`"
                table.append([f"**`{field}`:** {dtype_md}", "-"])

        return \
            f"{title_prefix} {self.name}\n\n" \
            f"Datatype class: *{self.type.capitalize()}*\n\n" \
            f"{table_to_markdown(headers, table, column_alignments)}"


class GraphQLSchemaParser:
    def __init__(self) -> None:
        self.schemas: Dict[str, GraphQLSchema] = {}
        self.scalars = SCALARS.copy()
        self.current_schema: Optional[GraphQLSchema] = None
        self.state = "none"
        self.current_type = ""
        self.field_state = "field"
        self.current_token = ""
        self.current_field = ""
        self.comment = False
        self.long_comment = False
        self.bracket_level = 0

    def read_character(self, character: str) -> None:

        if character == "\n":
            self.comment = False

        elif character == "#":
            self.comment = True

        if self.comment:
            return

        if self.bracket_level > 0 or character not in (" ", "{", ":", "}", "\n", "="):
            self.current_token += character
            if character == "(":
                self.bracket_level += 1
            elif character == ")":
                self.bracket_level -= 1
            if self.current_token == "\"\"\"":
                self.long_comment ^= True
                self.current_token = ""
            return

        if self.long_comment:
            self.current_token = ""
            return

        if self.state == "none":
            assert character in (" ", "\n")

            if self.current_token == '':
                pass
            elif self.current_token in ("type", "input", "enum", "scalar"):
                self.state = "name"
                self.current_type = self.current_token
                self.current_schema = GraphQLSchema(schema_type=self.current_type)
            else:
                raise ValueError(f"Unexpected token: {repr(self.current_token)}")

        elif self.state == "name":
            assert character in (" ", "\n", "{")
            assert self.current_schema

            self.current_schema.name = self.current_token

            if self.current_type == "scalar":
                self.state = "none"
                self.current_type = ""
                self.scalars.add(self.current_schema.name)
                self.schemas[self.current_schema.name] = self.current_schema
            else:
                self.state = "fields"
                self.field_state = "field"

        elif self.state == "fields":
            assert character in (":", "{", "}", "\n", " ", "=")
            assert self.current_type

            if character == "}":
                assert self.current_schema
                self.schemas[self.current_schema.name] = self.current_schema
                self.current_schema = None
                self.state = "none"
                self.current_type = ""
                self.field_state = "field"
            elif character == "=":
                self.comment = True
            elif self.current_token == '':
                pass
            else:
                assert character in (" ", ":", "\n", "=")

                if self.field_state == "field" and character in (":", " ", "\n"):
                    if self.current_type == "enum":
                        assert character in (" ", "\n")
                        self.current_schema.add_field(self.current_token, "")
                    else:
                        assert character in (" ", ":", "\n")
                        self.current_field = self.current_token
                        self.field_state = "dtype"
                elif self.field_state == "dtype" and character in ("\n", " "):
                    assert self.current_field
                    self.current_schema.add_field(self.current_field, self.current_token)
                    self.current_field = ""
                    self.field_state = "field"

        self.current_token = ""

    def to_markdown(self) -> str:
        return "\n\n".join([
            f"# Entrypoint Data Types",
            self.schemas.pop("Query").to_markdown(),
            *(int("Mutation" in self.schemas) * [self.schemas.pop("Mutation").to_markdown()]),
            "# Custom Data Types",
            *[schema.to_markdown(scalars=self.scalars) for schema in self.schemas.values()]
        ])


def convert_schema(schema_filename: str) -> str:
    with open(schema_filename, "rt") as file:
        schema = GraphQLSchemaParser()
        for line in file:
            for character in line:
                schema.read_character(character)
            schema.read_character("\n")
        return schema.to_markdown()


def table_to_markdown(
        headers: List[str],
        rows: List[List[str]],
        column_alignments: Optional[List[str]]
) -> str:
    return \
        "| " + " | ".join([str(value) for value in headers]) + " |\n" + \
        "| " + " | ".join(
            column_alignments if column_alignments else ["---"] * len(headers)
        ) + " |\n" + \
        "\n".join(["| " + " | ".join([str(value) for value in row]) + " |" for row in rows])


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description='Process some integers.')
    arg_parser.add_argument("--schema", "-s", dest="file_schema", default="./schema.graphql",
                            help="Input GraphQL schema.")
    arg_parser.add_argument("--output", "-o", dest="file_output", default="./schema.md",
                            help="Output markdown table schema.")
    args = arg_parser.parse_args()

    with open(args.file_output, "wt") as output_file:
        try:
            print("Parsing GraphQL schema...", end="")
            markdown_text: str = convert_schema(args.file_schema)
            print(" Done")
        except FileNotFoundError:
            print(f" Failed - Could not find input schema file '{args.file_output}'")
            sys.exit(1)

        try:
            print("Writing output schema as markdown tables...", end="")
            output_file.write(f"{markdown_text}\n")
            print(" Done")
        except Exception as e:
            print(f" Error:\n{str(e)}")

    sys.exit(0)
