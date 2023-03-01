# Copyright (c) 2014 Ahmed H. Ismail
# Copyright (c) 2023 spdx contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from typing import Any, List, Dict

from license_expression import get_spdx_licensing
from ply import yacc
from ply.yacc import LRParser

from spdx.datetime_conversions import datetime_from_str
from spdx.model.annotation import AnnotationType, Annotation
from spdx.model.document import Document, CreationInfo
from spdx.model.external_document_ref import ExternalDocumentRef
from spdx.model.extracted_licensing_info import ExtractedLicensingInfo
from spdx.model.file import File, FileType
from spdx.model.package import Package, PackageVerificationCode, PackagePurpose, ExternalPackageRef, \
    ExternalPackageRefCategory
from spdx.model.relationship import Relationship, RelationshipType
from spdx.model.snippet import Snippet
from spdx.model.spdx_no_assertion import SpdxNoAssertion
from spdx.model.spdx_none import SpdxNone
from spdx.model.version import Version
from spdx.parser.actor_parser import ActorParser
from spdx.parser.error import SPDXParsingError
from spdx.parser.logger import Logger
from spdx.parser.parsing_functions import construct_or_raise_parsing_error, raise_parsing_error_if_logger_has_messages
from spdx.parser.tagvalue.lexer.tagvalue import SPDXLexer
from spdx.parser.tagvalue.parser.helper_methods import grammar_rule, str_from_text, parse_checksum

CLASS_MAPPING = dict(File="files", Annotation="annotations", Relationship="relationships", Snippet="snippets",
                     Package="packages", ExtractedLicensingInfo="extracted_licensing_info")
ELEMENT_EXPECTED_START_TAG = dict(File="FileName", Annotation="Annotator", Relationship="Relationship",
                                  Snippet="SnippetSPDXID", Package="PackageName", ExtractedLicensingInfo="LicenseID")


class Parser(object):
    tokens: List[str]
    logger: Logger
    element_stack: List[Dict[str, str]]
    current_element: Dict[str, Any]
    creation_info: Dict[str, Any]
    elements_build: Dict[str, Any]
    lex: SPDXLexer
    yacc: LRParser

    def __init__(self, **kwargs):
        self.tokens = SPDXLexer.tokens
        self.logger = Logger()
        self.element_stack = []
        self.current_element = {"logger": Logger()}
        self.creation_info = {"logger": Logger()}
        self.elements_build = dict()
        self.lex = SPDXLexer()
        self.lex.build(reflags=re.UNICODE)
        self.yacc = yacc.yacc(module=self, **kwargs)

    @grammar_rule("start : start attrib ")
    def p_start_start_attrib(self, p):
        pass

    @grammar_rule("start : attrib ")
    def p_start_attrib(self, p):
        pass

    @grammar_rule("attrib : spdx_version\n| spdx_id\n| data_lics\n| doc_name\n| doc_comment\n| doc_namespace\n| "
                  "creator\n| created\n| creator_comment\n| lics_list_ver\n| ext_doc_ref\n"
                  # attributes for file 
                  "| file_name\n| file_type\n| file_checksum\n| file_conc\n| file_lics_info\n| file_cr_text\n"
                  "| file_lics_comment\n| file_attribution_text\n| file_notice\n| file_comment\n| file_contrib\n"
                  # attributes for annotation
                  "| annotator\n| annotation_date\n| annotation_comment\n| annotation_type\n| annotation_spdx_id\n"
                  # attributes for relationship
                  "| relationship\n"
                  # attributes for snippet
                  "| snip_spdx_id\n| snip_name\n| snip_comment\n| snippet_attribution_text\n| snip_cr_text\n"
                  "| snip_lic_comment\n| snip_file_spdx_id\n| snip_lics_conc\n| snip_lics_info\n| snip_byte_range\n"
                  "| snip_line_range\n"
                  # attributes for package
                  "| package_name\n| package_version\n| pkg_down_location\n| pkg_files_analyzed\n| pkg_home\n"
                  "| pkg_summary\n| pkg_src_info\n| pkg_file_name\n| pkg_supplier\n| pkg_orig\n| pkg_checksum\n"
                  "| pkg_verif\n| pkg_desc\n| pkg_comment\n| pkg_attribution_text\n| pkg_lic_decl\n| pkg_lic_conc\n"
                  "| pkg_lic_ff\n| pkg_lic_comment\n| pkg_cr_text\n| pkg_ext_ref\n| primary_package_purpose\n"
                  "| built_date\n| release_date\n| valid_until_date\n"
                  # attributes for extracted licensing info
                  "| extr_lic_id\n| extr_lic_text\n| extr_lic_name\n| lic_xref\n| lic_comment\n"
                  "| unknown_tag ")
    def p_attrib(self, p):
        pass

    # general parsing methods
    @grammar_rule("unknown_tag : UNKNOWN_TAG text_or_line\n | UNKNOWN_TAG DATE\n | UNKNOWN_TAG PERSON_VALUE")
    def p_unknown_tag(self, p):
        self.logger.append(f"Unknown tag provided in line {p.lineno(1)}")

    @grammar_rule("text_or_line : TEXT")
    def p_text(self, p):
        p[0] = str_from_text(p[1])

    @grammar_rule("text_or_line : LINE\n line_or_no_assertion : LINE\nline_or_no_assertion_or_none : text_or_line")
    def p_line(self, p):
        p[0] = p[1]

    @grammar_rule("license_or_no_assertion_or_none : NO_ASSERTION\n actor_or_no_assertion : NO_ASSERTION\n"
                  "line_or_no_assertion : NO_ASSERTION\n line_or_no_assertion_or_none : NO_ASSERTION")
    def p_no_assertion(self, p):
        p[0] = SpdxNoAssertion()

    @grammar_rule("license_or_no_assertion_or_none : NONE\n line_or_no_assertion_or_none : NONE")
    def p_none(self, p):
        p[0] = SpdxNone()

    @grammar_rule("license_or_no_assertion_or_none : LINE")
    def p_license(self, p):
        p[0] = get_spdx_licensing().parse(p[1])

    @grammar_rule("actor_or_no_assertion : PERSON_VALUE\n | ORG_VALUE")
    def p_actor_values(self, p):
        p[0] = ActorParser.parse_actor(p[1])

    @grammar_rule("spdx_id : SPDX_ID LINE")
    def p_spdx_id(self, p):
        # We assume that the documents spdx_id is defined first in the SPDXDocument, before any package or file
        # information. If this is not the case the parser will behave unexpectedly as the spdx_ids are assigned falsy.
        if "spdx_id" in self.creation_info:
            self.current_element["spdx_id"] = p[2]
        else:
            self.creation_info["spdx_id"] = p[2]

    # parsing methods for creation info / document level

    @grammar_rule("lics_list_ver : LIC_LIST_VER LINE")
    def p_license_list_version(self, p):
        try:
            self.creation_info["license_list_version"] = Version.from_string(p[2])
        except ValueError as err:
            self.creation_info["logger"].append(err.args[0])

    @grammar_rule("lics_list_ver : LIC_LIST_VER error")
    def p_license_list_version_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing LicenseListVersion: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("doc_comment : DOC_COMMENT text_or_line")
    def p_doc_comment(self, p):
        self.creation_info["document_comment"] = p[2]

    @grammar_rule("doc_comment : DOC_COMMENT error")
    def p_doc_comment_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing DocumentComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("doc_namespace : DOC_NAMESPACE LINE")
    def p_doc_namespace(self, p):
        self.creation_info["document_namespace"] = p[2]

    @grammar_rule("doc_namespace : DOC_NAMESPACE error")
    def p_doc_namespace_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing DocumentNamespace: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("data_lics : DOC_LICENSE LINE")
    def p_data_license(self, p):
        self.creation_info["data_license"] = p[2]

    @grammar_rule("data_lics : DOC_LICENSE error")
    def p_data_license_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing DataLicense: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("doc_name : DOC_NAME LINE")
    def p_doc_name(self, p):
        self.creation_info["name"] = p[2]

    @grammar_rule("doc_name : DOC_NAME error")
    def p_doc_name_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing DocumentName: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("ext_doc_ref : EXT_DOC_REF DOC_REF_ID DOC_URI EXT_DOC_REF_CHECKSUM")
    def p_external_document_ref(self, p):
        document_ref_id = p[2]
        document_uri = p[3]
        checksum = parse_checksum(self.creation_info["logger"], p[4])
        external_document_ref = ExternalDocumentRef(document_ref_id, document_uri, checksum)
        self.creation_info.setdefault("external_document_refs", []).append(external_document_ref)

    @grammar_rule("ext_doc_ref : EXT_DOC_REF error")
    def p_external_document_ref_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing ExternalDocumentRef: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("spdx_version : DOC_VERSION LINE")
    def p_spdx_version(self, p):
        self.creation_info["spdx_version"] = p[2]

    @grammar_rule("spdx_version : DOC_VERSION error")
    def p_spdx_version_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing SPDXVersion: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("creator_comment : CREATOR_COMMENT text_or_line")
    def p_creator_comment(self, p):
        self.creation_info["creator_comment"] = p[2]

    @grammar_rule("creator_comment : CREATOR_COMMENT error")
    def p_creator_comment_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing CreatorComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    def p_creator(self, p):
        """creator : CREATOR PERSON_VALUE\n| CREATOR TOOL_VALUE\n| CREATOR ORG_VALUE"""
        self.creation_info.setdefault("creators", []).append(ActorParser.parse_actor(p[2]))

    @grammar_rule("creator : CREATOR error")
    def p_creator_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing Creator: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("created : CREATED DATE")
    def p_created(self, p):
        self.creation_info["created"] = datetime_from_str(p[2])

    @grammar_rule("created : CREATED error")
    def p_created_error(self, p):
        self.creation_info["logger"].append(
            f"Error while parsing Created: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    # parsing methods for extracted licensing info

    @grammar_rule("extr_lic_id : LICS_ID LINE")
    def p_extracted_license_id(self, p):
        self.initialize_new_current_element(ExtractedLicensingInfo)
        self.current_element["license_id"] = p[2]

    @grammar_rule("extr_lic_id : LICS_ID error")
    def p_extracted_license_id_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseID: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("lic_xref : LICS_CRS_REF LINE")
    def p_extracted_cross_reference(self, p):
        self.check_that_current_element_matches_class_for_value(ExtractedLicensingInfo)
        self.current_element.setdefault("cross_references", []).append(p[2])

    @grammar_rule("lic_xref : LICS_CRS_REF error")
    def p_extracted_cross_reference_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseCrossReference: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("lic_comment : LICS_COMMENT text_or_line")
    def p_license_comment(self, p):
        self.check_that_current_element_matches_class_for_value(ExtractedLicensingInfo)
        self.current_element["comment"] = p[2]

    @grammar_rule("lic_comment : LICS_COMMENT error")
    def p_license_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("extr_lic_name : LICS_NAME line_or_no_assertion")
    def p_extracted_license_name(self, p):
        self.check_that_current_element_matches_class_for_value(ExtractedLicensingInfo)
        self.current_element["license_name"] = p[2]

    @grammar_rule("extr_lic_name : LICS_NAME error")
    def p_extracted_license_name_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseName: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("extr_lic_text : LICS_TEXT text_or_line")
    def p_extracted_license_text(self, p):
        self.check_that_current_element_matches_class_for_value(ExtractedLicensingInfo)
        self.current_element["extracted_text"] = p[2]

    @grammar_rule("extr_lic_text : LICS_TEXT error")
    def p_extracted_license_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing ExtractedText: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    # parsing methods for file

    @grammar_rule("file_name : FILE_NAME LINE")
    def p_file_name(self, p):
        self.initialize_new_current_element(File)
        self.current_element["name"] = p[2]

    @grammar_rule("file_name : FILE_NAME error")
    def p_file_name_error(self, p):
        self.initialize_new_current_element(File)
        self.current_element["logger"].append(
            f"Error while parsing {p[1]}: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_contrib : FILE_CONTRIB LINE")
    def p_file_contributor(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element.setdefault("contributors", []).append(p[2])

    @grammar_rule("file_contrib : FILE_CONTRIB error")
    def p_file_contributor_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileContributor: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_notice : FILE_NOTICE text_or_line")
    def p_file_notice(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element["notice"] = p[2]

    @grammar_rule("file_notice : FILE_NOTICE error")
    def p_file_notice_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileNotice: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_cr_text : FILE_CR_TEXT line_or_no_assertion_or_none")
    def p_file_copyright_text(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element["copyright_text"] = p[2]

    @grammar_rule("file_cr_text : FILE_CR_TEXT error")
    def p_file_copyright_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileCopyrightText: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_lics_comment : FILE_LICS_COMMENT text_or_line")
    def p_file_license_comment(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element["license_comment"] = p[2]

    @grammar_rule("file_lics_comment : FILE_LICS_COMMENT error")
    def p_file_license_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseComments in file: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("file_attribution_text : FILE_ATTRIBUTION_TEXT text_or_line")
    def p_file_attribution_text(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element.setdefault("attribution_texts", []).append(p[2])

    @grammar_rule("file_attribution_text : FILE_ATTRIBUTION_TEXT error")
    def p_file_attribution_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileAttributionText: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_lics_info : FILE_LICS_INFO license_or_no_assertion_or_none")
    def p_file_license_info(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        if p[2] == SpdxNone() or p[2] == SpdxNoAssertion():
            self.current_element["license_info_in_file"] = p[2]
            return
        self.current_element.setdefault("license_info_in_file", []).append(p[2])

    @grammar_rule("file_lics_info : FILE_LICS_INFO error")
    def p_file_license_info_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseInfoInFile: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_comment : FILE_COMMENT text_or_line")
    def p_file_comment(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element["comment"] = p[2]

    @grammar_rule("file_comment : FILE_COMMENT error")
    def p_file_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_type : FILE_TYPE file_type_value")
    def p_file_type(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element.setdefault("file_type", []).append(FileType[p[2]])

    @grammar_rule("file_type : FILE_TYPE error")
    def p_file_type_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FileType: Token did not match any of the valid values. Line: {p.lineno(1)}")

    @grammar_rule(
        "file_type_value : SOURCE\n| BINARY\n| ARCHIVE\n | APPLICATION\n | AUDIO\n | IMAGE\n | FILETYPE_TEXT\n| VIDEO\n"
        " | DOCUMENTATION\n| SPDX \n| OTHER ")
    def p_file_type_value(self, p):
        p[0] = p[1]

    @grammar_rule("file_checksum : FILE_CHECKSUM CHECKSUM")
    def p_file_checksum(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        checksum = parse_checksum(self.current_element["logger"], p[2])
        self.current_element.setdefault("checksums", []).append(checksum)

    @grammar_rule("file_checksum : FILE_CHECKSUM error")
    def p_file_checksum_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing Checksum in file: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("file_conc : FILE_LICS_CONC license_or_no_assertion_or_none")
    def p_file_license_concluded(self, p):
        self.check_that_current_element_matches_class_for_value(File)
        self.current_element["license_concluded"] = p[2]

    @grammar_rule("file_conc : FILE_LICS_CONC error")
    def p_file_license_concluded_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseConcluded in file: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    # parsing methods for package

    @grammar_rule("package_name : PKG_NAME LINE")
    def p_package_name(self, p):
        self.initialize_new_current_element(Package)
        self.current_element["name"] = p[2]

    @grammar_rule("package_name : PKG_NAME error")
    def p_package_name_error(self, p):
        self.initialize_new_current_element(Package)
        self.current_element["logger"].append(
            f"Error while parsing {p[1]}: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_desc : PKG_DESC text_or_line")
    def p_pkg_description(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["description"] = p[2]

    @grammar_rule("pkg_desc : PKG_DESC error")
    def p_pkg_description_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageDescription: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_comment : PKG_COMMENT text_or_line")
    def p_pkg_comment(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["comment"] = p[2]

    @grammar_rule("pkg_comment : PKG_COMMENT error")
    def p_pkg_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_attribution_text : PKG_ATTRIBUTION_TEXT text_or_line")
    def p_pkg_attribution_text(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element.setdefault("attribution_texts", []).append(p[2])

    @grammar_rule("pkg_attribution_text : PKG_ATTRIBUTION_TEXT error")
    def p_pkg_attribution_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageAttributionText: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_summary : PKG_SUM text_or_line")
    def p_pkg_summary(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["summary"] = p[2]

    @grammar_rule("pkg_summary : PKG_SUM error")
    def p_pkg_summary_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageSummary: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_cr_text : PKG_CPY_TEXT line_or_no_assertion_or_none")
    def p_pkg_copyright_text(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["copyright_text"] = p[2]

    @grammar_rule("pkg_cr_text : PKG_CPY_TEXT error")
    def p_pkg_copyright_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageCopyrightText: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_ext_ref : PKG_EXT_REF LINE PKG_EXT_REF_COMMENT text_or_line\n | PKG_EXT_REF LINE")
    def p_pkg_external_refs(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        category, reference_type, locator = p[2].split(" ")
        comment = None
        if len(p) == 5:
            comment = p[4]
        try:
            category = ExternalPackageRefCategory[category.replace("-", "_")]
        except KeyError:
            self.current_element["logger"].append(f"Invalid ExternalPackageRefCategory: {category}")
            return
        try:
            external_package_ref = construct_or_raise_parsing_error(ExternalPackageRef,
                                                                    {"category": category,
                                                                     "reference_type": reference_type,
                                                                     "locator": locator,
                                                                     "comment": comment})
        except SPDXParsingError as err:
            self.current_element["logger"].append(err.get_messages())
            return
        self.current_element.setdefault("external_references", []).append(external_package_ref)

    @grammar_rule("pkg_ext_ref : PKG_EXT_REF error")
    def p_pkg_external_refs_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing ExternalRef in package: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_lic_comment : PKG_LICS_COMMENT text_or_line")
    def p_pkg_license_comment(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["license_comment"] = p[2]

    @grammar_rule("pkg_lic_comment : PKG_LICS_COMMENT error")
    def p_pkg_license_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageLicenseComments: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_lic_decl : PKG_LICS_DECL license_or_no_assertion_or_none")
    def p_pkg_license_declared(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["license_declared"] = p[2]

    @grammar_rule("pkg_lic_decl : PKG_LICS_DECL error")
    def p_pkg_license_declared_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseDeclared in package: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_lic_ff : PKG_LICS_FFILE license_or_no_assertion_or_none")
    def p_pkg_license_info_from_file(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        if p[2] == SpdxNone() or p[2] == SpdxNoAssertion():
            self.current_element["license_info_from_files"] = p[2]
        else:
            self.current_element.setdefault("license_info_from_files", []).append(p[2])

    @grammar_rule("pkg_lic_ff : PKG_LICS_FFILE error")
    def p_pkg_license_info_from_file_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseInfoFromFiles in package: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_lic_conc : PKG_LICS_CONC license_or_no_assertion_or_none")
    def p_pkg_license_concluded(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["license_concluded"] = p[2]

    @grammar_rule("pkg_lic_conc : PKG_LICS_CONC error")
    def p_pkg_license_concluded_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing LicenseConcluded in package: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_src_info : PKG_SRC_INFO text_or_line")
    def p_pkg_source_info(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["source_info"] = p[2]

    @grammar_rule("pkg_src_info : PKG_SRC_INFO error")
    def p_pkg_source_info_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageSourceInfo: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_checksum : PKG_CHECKSUM CHECKSUM")
    def p_pkg_checksum(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        checksum = parse_checksum(self.current_element["logger"], p[2])
        self.current_element.setdefault("checksums", []).append(checksum)

    @grammar_rule("pkg_checksum : PKG_CHECKSUM error")
    def p_pkg_checksum_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageChecksum: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_verif : PKG_VERF_CODE LINE")
    def p_pkg_verification_code(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        verif_code_regex = re.compile(r"([0-9a-f]+)\s*(\(excludes:\s*(.+)\))?", re.UNICODE)
        verif_code_code_grp = 1
        verif_code_exc_files_grp = 3
        match = verif_code_regex.match(p[2])
        value = match.group(verif_code_code_grp)
        excluded_files = None
        if match.group(verif_code_exc_files_grp):
            excluded_files = match.group(verif_code_exc_files_grp).split(",")
        self.current_element["verification_code"] = PackageVerificationCode(value, excluded_files)

    @grammar_rule("pkg_verif : PKG_VERF_CODE error")
    def p_pkg_verification_code_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageVerificationCode: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_home : PKG_HOME line_or_no_assertion_or_none")
    def p_pkg_homepage(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["homepage"] = p[2]

    @grammar_rule("pkg_home : PKG_HOME error")
    def p_pkg_homepage_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageHomePage: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_down_location : PKG_DOWN line_or_no_assertion_or_none")
    def p_pkg_download_location(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["download_location"] = p[2]

    @grammar_rule("pkg_down_location : PKG_DOWN error")
    def p_pkg_download_location_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageDownloadLocation: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_files_analyzed : PKG_FILES_ANALYZED LINE")
    def p_pkg_files_analyzed(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        if p[2] in ['false', 'False']:
            self.current_element["files_analyzed"] = False
        if p[2] in ['true', 'True']:
            self.current_element["files_analyzed"] = True

    @grammar_rule("pkg_files_analyzed : PKG_FILES_ANALYZED error")
    def p_pkg_files_analyzed_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing FilesAnalyzed in package: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("pkg_orig : PKG_ORIG actor_or_no_assertion")
    def p_pkg_originator(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["originator"] = p[2]

    @grammar_rule("pkg_orig : PKG_ORIG error")
    def p_pkg_originator_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageOriginator: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_supplier : PKG_SUPPL actor_or_no_assertion")
    def p_pkg_supplier(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["supplier"] = p[2]

    @grammar_rule("pkg_supplier : PKG_SUPPL error")
    def p_pkg_supplier_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageSupplier: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("pkg_file_name : PKG_FILE_NAME LINE")
    def p_pkg_file_name(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["file_name"] = p[2]

    @grammar_rule("pkg_file_name : PKG_FILE_NAME error")
    def p_pkg_file_name_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageFileName: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("package_version : PKG_VERSION LINE")
    def p_package_version(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["version"] = p[2]

    @grammar_rule("package_version : PKG_VERSION error")
    def p_package_version_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PackageVersion: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("primary_package_purpose : PRIMARY_PACKAGE_PURPOSE primary_package_purpose_value")
    def p_primary_package_purpose(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["primary_package_purpose"] = PackagePurpose[p[2].replace("-", "_")]

    @grammar_rule("primary_package_purpose : PRIMARY_PACKAGE_PURPOSE error")
    def p_primary_package_purpose_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing PrimaryPackagePurpose: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("primary_package_purpose_value : APPLICATION\n | FRAMEWORK\n | LIBRARY\n | CONTAINER\n "
                  "| OPERATING_SYSTEM \n | DEVICE \n| FIRMWARE\n | SOURCE\n | ARCHIVE\n | FILE\n | INSTALL\n | OTHER")
    def p_primary_package_purpose_value(self, p):
        p[0] = p[1]

    @grammar_rule("built_date : BUILT_DATE DATE")
    def p_built_date(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["built_date"] = datetime_from_str(p[2])

    @grammar_rule("built_date : BUILT_DATE error")
    def p_built_date_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing BuiltDate: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("release_date : RELEASE_DATE DATE")
    def p_release_date(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["release_date"] = datetime_from_str(p[2])

    @grammar_rule("release_date : RELEASE_DATE error")
    def p_release_date_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing ReleaseDate: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("valid_until_date : VALID_UNTIL_DATE DATE")
    def p_valid_until_date(self, p):
        self.check_that_current_element_matches_class_for_value(Package)
        self.current_element["valid_until_date"] = datetime_from_str(p[2])

    @grammar_rule("valid_until_date : VALID_UNTIL_DATE error")
    def p_valid_until_date_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing ValidUntilDate: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    # parsing methods for snippet
    @grammar_rule("snip_spdx_id : SNIPPET_SPDX_ID LINE")
    def p_snippet_spdx_id(self, p):
        self.initialize_new_current_element(Snippet)
        self.current_element["spdx_id"] = p[2]

    @grammar_rule("snip_spdx_id : SNIPPET_SPDX_ID error")
    def p_snippet_spdx_id_error(self, p):
        self.initialize_new_current_element(Snippet)
        self.current_element["logger"].append(
            f"Error while parsing SnippetSPDXID: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("snip_name : SNIPPET_NAME LINE")
    def p_snippet_name(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["name"] = p[2]

    @grammar_rule("snip_name : SNIPPET_NAME error")
    def p_snippet_name_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetName: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("snip_comment : SNIPPET_COMMENT text_or_line")
    def p_snippet_comment(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["comment"] = p[2]

    @grammar_rule("snip_comment : SNIPPET_COMMENT error")
    def p_snippet_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("snippet_attribution_text : SNIPPET_ATTRIBUTION_TEXT text_or_line")
    def p_snippet_attribution_text(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element.setdefault("attribution_texts", []).append(p[2])

    @grammar_rule("snippet_attribution_text : SNIPPET_ATTRIBUTION_TEXT error")
    def p_snippet_attribution_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetAttributionText: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_cr_text : SNIPPET_CR_TEXT line_or_no_assertion_or_none")
    def p_snippet_copyright_text(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["copyright_text"] = p[2]

    @grammar_rule("snip_cr_text : SNIPPET_CR_TEXT error")
    def p_snippet_copyright_text_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetCopyrightText: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_lic_comment : SNIPPET_LICS_COMMENT text_or_line")
    def p_snippet_license_comment(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["license_comment"] = p[2]

    @grammar_rule("snip_lic_comment : SNIPPET_LICS_COMMENT error")
    def p_snippet_license_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetLicenseComments: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_file_spdx_id : SNIPPET_FILE_SPDXID LINE")
    def p_snippet_from_file_spdxid(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["file_spdx_id"] = p[2]

    @grammar_rule("snip_file_spdx_id : SNIPPET_FILE_SPDXID error")
    def p_snippet_from_file_spdxid_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetFromFileSPDXID: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_lics_conc : SNIPPET_LICS_CONC license_or_no_assertion_or_none")
    def p_snippet_concluded_license(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        self.current_element["license_concluded"] = p[2]

    @grammar_rule("snip_lics_conc : SNIPPET_LICS_CONC error")
    def p_snippet_concluded_license_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetLicenseConcluded: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_lics_info : SNIPPET_LICS_INFO license_or_no_assertion_or_none")
    def p_snippet_license_info(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        if p[2] == SpdxNone() or p[2] == SpdxNoAssertion():
            self.current_element["license_info_in_snippet"] = p[2]
        else:
            self.current_element.setdefault("license_info_in_snippet", []).append(p[2])

    @grammar_rule("snip_lics_info : SNIPPET_LICS_INFO error")
    def p_snippet_license_info_error(self, p):

        self.current_element["logger"].append(
            f"Error while parsing LicenseInfoInSnippet: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    @grammar_rule("snip_byte_range : SNIPPET_BYTE_RANGE LINE")
    def p_snippet_byte_range(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        range_re = re.compile(r"^(\d+):(\d+)$", re.UNICODE)
        if not range_re.match(p[2].strip()):
            self.current_element["logger"].append("Value for SnippetByteRange doesn't match valid range pattern.")
            return
        startpoint = int(p[2].split(":")[0])
        endpoint = int(p[2].split(":")[-1])
        self.current_element["byte_range"] = startpoint, endpoint

    @grammar_rule("snip_byte_range : SNIPPET_BYTE_RANGE error")
    def p_snippet_byte_range_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetByteRange: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("snip_line_range : SNIPPET_LINE_RANGE LINE")
    def p_snippet_line_range(self, p):
        self.check_that_current_element_matches_class_for_value(Snippet)
        range_re = re.compile(r"^(\d+):(\d+)$", re.UNICODE)
        if not range_re.match(p[2].strip()):
            self.current_element["logger"].append("Value for SnippetLineRange doesn't match valid range pattern.")
            return
        startpoint = int(p[2].split(":")[0])
        endpoint = int(p[2].split(":")[1])
        self.current_element["line_range"] = startpoint, endpoint

    @grammar_rule("snip_line_range : SNIPPET_LINE_RANGE error")
    def p_snippet_line_range_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SnippetLineRange: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    # parsing methods for annotation
    def p_annotator(self, p):
        """annotator : ANNOTATOR PERSON_VALUE\n| TOOL_VALUE\n| ORG_VALUE"""
        self.initialize_new_current_element(Annotation)
        try:
            self.current_element["annotator"] = ActorParser.parse_actor(p[2])
        except SPDXParsingError as err:
            self.current_element["logger"].append(err.get_messages())

    @grammar_rule("annotator : ANNOTATOR error")
    def p_annotator_error(self, p):
        self.initialize_new_current_element(Annotation)
        self.current_element["logger"].append(
            f"Error while parsing {p[1]}: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("annotation_date : ANNOTATION_DATE DATE")
    def p_annotation_date(self, p):
        self.check_that_current_element_matches_class_for_value(Annotation)
        self.current_element["annotation_date"] = datetime_from_str(p[2])

    @grammar_rule("annotation_date : ANNOTATION_DATE error")
    def p_annotation_date_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing AnnotationDate: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("annotation_comment : ANNOTATION_COMMENT text_or_line")
    def p_annotation_comment(self, p):
        self.check_that_current_element_matches_class_for_value(Annotation)
        self.current_element["annotation_comment"] = p[2]

    @grammar_rule("annotation_comment : ANNOTATION_COMMENT error")
    def p_annotation_comment_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing AnnotationComment: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("annotation_type : ANNOTATION_TYPE annotation_type_value")
    def p_annotation_type(self, p):
        self.check_that_current_element_matches_class_for_value(Annotation)
        self.current_element["annotation_type"] = AnnotationType[p[2]]

    @grammar_rule("annotation_type : ANNOTATION_TYPE error")
    def p_annotation_type_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing AnnotationType: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("annotation_type_value : OTHER\n| REVIEW")
    def p_annotation_type_value(self, p):
        p[0] = p[1]

    @grammar_rule("annotation_spdx_id : ANNOTATION_SPDX_ID LINE")
    def p_annotation_spdx_id(self, p):
        self.current_element["spdx_id"] = p[2]

    @grammar_rule("annotation_spdx_id : ANNOTATION_SPDX_ID error")
    def p_annotation_spdx_id_error(self, p):
        self.current_element["logger"].append(
            f"Error while parsing SPDXREF in annotation: Token did not match specified grammar rule. "
            f"Line: {p.lineno(1)}")

    # parsing methods for relationship
    @grammar_rule("relationship : RELATIONSHIP relationship_value RELATIONSHIP_COMMENT text_or_line\n "
                  "| RELATIONSHIP relationship_value")
    def p_relationship(self, p):
        self.initialize_new_current_element(Relationship)
        try:
            spdx_element_id, relationship_type, related_spdx_element_id = p[2].split(" ")
        except ValueError:
            self.current_element["logger"].append(
                f"Relationship couldn't be split in spdx_element_id, relationship_type and "
                f"related_spdx_element. Line: {p.lineno(1)}")
            return
        try:
            self.current_element["relationship_type"] = RelationshipType[relationship_type]
        except KeyError:
            self.current_element["logger"].append(f"Invalid RelationshipType {relationship_type}. Line: {p.lineno(1)}")
        if related_spdx_element_id == "NONE":
            related_spdx_element_id = SpdxNone()
        if related_spdx_element_id == "NOASSERTION":
            related_spdx_element_id = SpdxNoAssertion()
        self.current_element["related_spdx_element_id"] = related_spdx_element_id
        self.current_element["spdx_element_id"] = spdx_element_id
        if len(p) == 5:
            self.current_element["comment"] = p[4]

    @grammar_rule("relationship : RELATIONSHIP error")
    def p_relationship_error(self, p):
        self.initialize_new_current_element(Relationship)
        self.current_element["logger"].append(
            f"Error while parsing Relationship: Token did not match specified grammar rule. Line: {p.lineno(1)}")

    @grammar_rule("relationship_value : DOC_REF_ID LINE")
    def p_relationship_value_with_doc_ref(self, p):

        p[0] = p[1] + ":" + p[2]

    @grammar_rule("relationship_value : LINE")
    def p_relationship_value_without_doc_ref(self, p):

        p[0] = p[1]

    def p_error(self, p):
        pass

    def parse(self, text):
        self.yacc.parse(text, lexer=self.lex)
        self.construct_current_element()
        try:
            raise_parsing_error_if_logger_has_messages(self.creation_info.pop("logger"), "CreationInfo")
        except SPDXParsingError as err:
            self.logger.append(err.get_messages())
        raise_parsing_error_if_logger_has_messages(self.logger)
        creation_info = construct_or_raise_parsing_error(CreationInfo, self.creation_info)
        self.elements_build["creation_info"] = creation_info
        document = construct_or_raise_parsing_error(Document, self.elements_build)
        return document

    def construct_current_element(self):
        if "class" not in self.current_element:
            self.current_element = {"logger": Logger()}
            return
        class_name = self.current_element.pop("class")
        try:
            raise_parsing_error_if_logger_has_messages(self.current_element.pop("logger"), class_name.__name__)
        except SPDXParsingError as err:
            self.logger.append(err.get_messages())
            self.current_element = {"logger": Logger()}
            return
        try:
            self.elements_build.setdefault(CLASS_MAPPING[class_name.__name__], []).append(
                construct_or_raise_parsing_error(class_name, self.current_element))
            if class_name == File:
                self.check_for_preceding_package_and_build_contains_relationship()
        except SPDXParsingError as err:
            self.logger.append(err.get_messages())
        self.current_element = {"logger": Logger()}

    def check_that_current_element_matches_class_for_value(self, expected_class):
        if "class" not in self.current_element:
            self.logger.append(
                f"Element {expected_class.__name__} is not the current element in scope, probably the expected tag to "
                f"start the element ({ELEMENT_EXPECTED_START_TAG[expected_class.__name__]}) is missing.")
        elif expected_class != self.current_element["class"]:
            self.logger.append(
                f"Element {expected_class.__name__} is not the current element in scope, probably the expected tag to "
                f"start the element ({ELEMENT_EXPECTED_START_TAG[expected_class.__name__]}) is missing.")

    def initialize_new_current_element(self, class_name: Any):
        if "class" in self.current_element and "spdx_id" in self.current_element:
            self.element_stack.append({self.current_element["class"]: self.current_element["spdx_id"]})
        self.construct_current_element()
        self.current_element["class"] = class_name

    def check_for_preceding_package_and_build_contains_relationship(self):
        file_spdx_id = self.current_element["spdx_id"]
        if "packages" not in self.elements_build:
            return
        package_spdx_id = self.elements_build["packages"][-1].spdx_id
        relationship = Relationship(package_spdx_id, RelationshipType.CONTAINS, file_spdx_id)
        if relationship not in self.elements_build["relationships"]:
            self.elements_build.setdefault("relationships", []).append(relationship)
