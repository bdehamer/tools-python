# Copyright (c) 2022 spdx contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Dict, List, Optional

from src.model.relationship import Relationship, RelationshipType
from src.model.typing.constructor_type_errors import ConstructorTypeErrors
from src.parser.error import SPDXParsingError
from src.parser.json.dict_parsing_functions import transform_json_str_to_enum_name, \
    try_construction_raise_parsing_error, try_parse_required_field_append_logger_when_failing
from src.parser.logger import Logger


class RelationshipParser:
    logger: Logger

    def __init__(self):
        self.logger = Logger()

    def parse_all_relationships(self, input_doc_dict: Dict) -> List[Relationship]:
        relationships_list = []
        relationships_dicts: List[Dict] = input_doc_dict.get("relationships")
        if relationships_dicts:
            try:
                relationships = self.parse_relationships(relationship_dicts=relationships_dicts)
                relationships_list.extend(relationships)
            except SPDXParsingError as err:
                self.logger.append_all(err.get_messages())

        document_describes: List[str] = input_doc_dict.get("documentDescribes")
        doc_spdx_id: str = input_doc_dict.get("SPDXID")
        if document_describes:
            try:
                describes_relationships = self.parse_document_describes(doc_spdx_id=doc_spdx_id,
                                                                        described_spdx_ids=document_describes,
                                                                        created_relationships=relationships_list)
                relationships_list.extend(describes_relationships)
            except SPDXParsingError as err:
                self.logger.append_all(err.get_messages())

        package_dicts: List[Dict] = input_doc_dict.get("packages")
        if package_dicts:
            try:
                contains_relationships = self.parse_has_files(package_dicts=package_dicts,
                                                              created_relationships=relationships_list)
                relationships_list.extend(contains_relationships)
            except SPDXParsingError as err:
                self.logger.append_all(err.get_messages())

        file_dicts: List[Dict] = input_doc_dict.get("files")
        if file_dicts:
            # not implemented yet, deal with deprecated fields in file
            try:
                dependency_relationships = self.parse_file_dependencies(file_dicts=file_dicts)
                relationships_list.extend(dependency_relationships)
            except SPDXParsingError as err:
                self.logger.append_all(err.get_messages())
            generated_relationships = self.parse_artifact_of(file_dicts=file_dicts)

        if self.logger.has_messages():
            raise SPDXParsingError(self.logger.get_messages())

        return relationships_list

    def parse_relationships(self, relationship_dicts: List[Dict]) -> List[Relationship]:
        logger = Logger()
        relationship_list = []
        for relationship_dict in relationship_dicts:
            try:
                relationship_list.append(self.parse_relationship(relationship_dict))
            except SPDXParsingError as err:
                logger.append_all(err.get_messages())
        if logger.has_messages():
            raise SPDXParsingError(logger.has_messages())
        return relationship_list

    def parse_relationship(self, relationship_dict: Dict) -> Relationship:
        logger = Logger()
        spdx_element_id: str = relationship_dict.get("spdxElementId")
        related_spdx_element: str = relationship_dict.get("relatedSpdxElement")
        relationship_type: Optional[RelationshipType] = try_parse_required_field_append_logger_when_failing(
            logger=logger, field=relationship_dict.get("relationshipType"),
            method_to_parse=self.parse_relationship_type)
        relationship_comment: str = relationship_dict.get("comment")
        if logger.has_messages():
            raise SPDXParsingError([f"Error while parsing relationship: {logger.get_messages()}"])

        relationship = try_construction_raise_parsing_error(Relationship, dict(spdx_element_id=spdx_element_id,
                                                                               relationship_type=relationship_type,
                                                                               related_spdx_element_id=related_spdx_element,
                                                                               comment=relationship_comment))
        return relationship

    @staticmethod
    def parse_relationship_type(relationship_type_str: str) -> RelationshipType:
        try:
            relationship_type = RelationshipType[transform_json_str_to_enum_name(relationship_type_str)]
        except KeyError:
            raise SPDXParsingError([f"RelationshipType {relationship_type_str} is not valid."])
        except AttributeError:
            raise SPDXParsingError([f"RelationshipType must be str, not {type(relationship_type_str).__name__}."])
        return relationship_type

    def parse_document_describes(self, doc_spdx_id: str, described_spdx_ids: List[str],
                                 created_relationships: List[Relationship]) -> List[Relationship]:
        logger = Logger()
        describes_relationships = []
        for spdx_id in described_spdx_ids:
            try:
                describes_relationship = Relationship(spdx_element_id=doc_spdx_id,
                                                      relationship_type=RelationshipType.DESCRIBES,
                                                      related_spdx_element_id=spdx_id)
            except ConstructorTypeErrors as err:
                logger.append(err.get_messages())
                continue
            if not self.check_if_relationship_exists(describes_relationship, created_relationships):
                describes_relationships.append(describes_relationship)
        if logger.has_messages():
            raise SPDXParsingError([f"Error while creating describes_relationship : {logger.get_messages()}"])

        return describes_relationships

    def parse_has_files(self, package_dicts: List[Dict], created_relationships: List[Relationship]) -> List[
        Relationship]:
        logger = Logger()
        contains_relationships = []
        for package in package_dicts:
            package_spdx_id = package.get("SPDXID")
            contained_files = package.get("hasFiles")
            if not contained_files:
                continue
            for file_spdx_id in contained_files:
                try:
                    contains_relationship = Relationship(spdx_element_id=package_spdx_id,
                                                         relationship_type=RelationshipType.CONTAINS,
                                                         related_spdx_element_id=file_spdx_id)
                except ConstructorTypeErrors as err:
                    logger.append(err.get_messages())
                    continue
                if not self.check_if_relationship_exists(relationship=contains_relationship,
                                                         created_relationships=created_relationships):
                    contains_relationships.append(contains_relationship)
        if logger.has_messages():
            raise SPDXParsingError([f"Error while creating describes_relationship : {logger.get_messages()}"])

        return contains_relationships

    def check_if_relationship_exists(self, relationship: Relationship,
                                     created_relationships: List[Relationship]) -> bool:
        created_relationships_without_comment: List[Relationship] = self.ignore_any_comments_in_relationship_list(
            created_relationships)
        if relationship in created_relationships_without_comment:
            return True
        relationship_converted: Relationship = self.convert_relationship(relationship)
        if relationship_converted in created_relationships_without_comment:
            return True

        return False

    @staticmethod
    def ignore_any_comments_in_relationship_list(created_relationships: List[Relationship]) -> List[Relationship]:
        relationships_without_comment = [Relationship(relationship_type=relationship.relationship_type,
                                                      related_spdx_element_id=relationship.related_spdx_element_id,
                                                      spdx_element_id=relationship.spdx_element_id) for relationship in
                                         created_relationships]
        return relationships_without_comment

    def convert_relationship(self, relationship: Relationship) -> Relationship:
        return Relationship(related_spdx_element_id=relationship.spdx_element_id,
                            spdx_element_id=relationship.related_spdx_element_id,
                            relationship_type=self.convert_relationship_types[relationship.relationship_type],
                            comment=relationship.comment)

    convert_relationship_types = {RelationshipType.DESCRIBES: RelationshipType.DESCRIBED_BY,
                                  RelationshipType.DESCRIBED_BY: RelationshipType.DESCRIBES,
                                  RelationshipType.CONTAINS: RelationshipType.CONTAINED_BY,
                                  RelationshipType.CONTAINED_BY: RelationshipType.CONTAINS}

    @staticmethod
    def parse_file_dependencies(file_dicts: List[Dict]) -> List[Relationship]:
        logger = Logger()
        dependency_relationships = []
        for file in file_dicts:
            file_spdx_id: str = file.get("SPDXID")
            dependency_of: List[str] = file.get("fileDependencies")
            if not dependency_of:
                continue
            for dependency in dependency_of:
                try:
                    dependency_relationship = Relationship(spdx_element_id=dependency,
                                                           relationship_type=RelationshipType.DEPENDENCY_OF,
                                                           related_spdx_element_id=file_spdx_id)
                except ConstructorTypeErrors as err:
                    logger.append_all(err.get_messages())
                    continue
                dependency_relationships.append(dependency_relationship)
        if logger.has_messages():
            raise SPDXParsingError([f"Error while creating dependency relationships: {logger.get_messages()}"])
        return dependency_relationships

    @staticmethod
    def parse_artifact_of(file_dicts: List[Dict]) -> List[Relationship]:
        generated_relationships = []
        # TODO: artifactOfs is deprecated and should be converted to an external package and a generated from relationship
        return generated_relationships
