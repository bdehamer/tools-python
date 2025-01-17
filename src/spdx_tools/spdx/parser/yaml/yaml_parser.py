# SPDX-FileCopyrightText: 2023 spdx contributors
#
# SPDX-License-Identifier: Apache-2.0
import yaml
from beartype.typing import Dict

from spdx_tools.spdx.model import Document
from spdx_tools.spdx.parser.jsonlikedict.json_like_dict_parser import JsonLikeDictParser


def parse_from_file(file_name: str) -> Document:
    with open(file_name) as file:
        input_doc_as_dict: Dict = yaml.safe_load(file)

    return JsonLikeDictParser().parse(input_doc_as_dict)
