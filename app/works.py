import requests
from vivo_uri import to_hash_identifier, PREFIX_DOCUMENT, PREFIX_PERSON, PREFIX_ORGANIZATION, PREFIX_JOURNAL
from rdflib import RDFS, RDF, XSD, Literal
from vivo_namespace import VIVO, VCARD, OBO, BIBO, FOAF, SKOS
import app.vivo_namespace as ns
from utility import join_if_not_empty
import re
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.latexenc import unicode_to_latex, unicode_to_crappy_latex1, unicode_to_crappy_latex2
import itertools
from utility import add_date


def crosswalk_works(orcid_profile, person_uri, graph):
    # Work metadata may be available from the orcid profile, bibtex contained in the orcid profile, and/or a crossref
    # record. The preferred order (in general) for getting metadata is crossref, bibtex, orcid.

    # Note that datacite records were considered, but not found to have additional/better metadata.

    #Publications
    for work in ((orcid_profile["orcid-profile"].get("orcid-activities") or {}).get("orcid-works") or {})\
            .get("orcid-work", []):
        ##Extract
        #Get external identifiers so that can get DOI
        external_identifiers = _get_work_identifiers(work)
        doi = external_identifiers.get("DOI")
        crossref_record = fetch_crossref_doi(doi) if doi else {}

        #Bibtex
        bibtex = _parse_bibtex(work)

        #Work Type
        work_type = work["work-type"]

        #Title
        title = _get_crossref_title(crossref_record) or bibtex.get("title") or _get_orcid_title(work)

        work_uri = ns.D[to_hash_identifier(PREFIX_DOCUMENT, (title, work_type))]

        #Publication date
        (publication_year, publication_month, publication_day) = _get_crossref_publication_date(crossref_record) \
            or _get_publication_date(work)

        #Subjects
        subjects = crossref_record["subject"] if crossref_record and "subject" in crossref_record else None

        #Authors (an array of (first_name, surname))
        authors = _get_crossref_authors(crossref_record)
        #TODO: Get from bibtext and ORCID profile as alternates. See #5.

        #Publisher
        publisher = bibtex.get("publisher")
        #TODO: Get from crossref as preferred. See #10.

        #Journal
        journal = bibtex.get("journal")
        #TODO: Get from crossref as preferred, orcid profile as alterate. See #11.

        #Volume
        volume = bibtex.get("volume")
        #Number
        number = bibtex.get("number")
        #Pages
        pages = bibtex.get("pages")
        start_page = None
        end_page = None
        if pages and "-" in pages:
            (start_page, end_page) = re.split(" *-+ *", pages, maxsplit=2)


        ##Add triples
        #Title
        graph.add((work_uri, RDFS.label, Literal(title)))
        #Person (via Authorship)
        authorship_uri = work_uri + "-auth"
        graph.add((authorship_uri, RDF.type, VIVO.Authorship))
        graph.add((authorship_uri, VIVO.relates, work_uri))
        graph.add((authorship_uri, VIVO.relates, person_uri))
        #Other authors
        if authors:
            person_surname = orcid_profile["orcid-profile"]["orcid-bio"]["personal-details"]["family-name"]["value"]
            for (first_name, surname) in authors:
                if not person_surname.lower() == surname.lower():
                    author_uri = ns.D[to_hash_identifier(PREFIX_PERSON, (first_name, surname))]
                    graph.add((author_uri, RDF.type, FOAF.Person))
                    full_name = join_if_not_empty((first_name, surname))
                    graph.add((author_uri, RDFS.label, Literal(full_name)))

                    authorship_uri = author_uri + "-auth"
                    graph.add((authorship_uri, RDF.type, VIVO.Authorship))
                    graph.add((authorship_uri, VIVO.relates, work_uri))
                    graph.add((authorship_uri, VIVO.relates, author_uri))

        #Date
        date_uri = work_uri + "-date"
        graph.add((work_uri, VIVO.dateTimeValue, date_uri))
        add_date(date_uri, publication_year, graph, publication_month, publication_day)
        #Subjects
        if subjects:
            for subject in subjects:
                subject_uri = ns.D[to_hash_identifier("sub", (subject,))]
                graph.add((work_uri, VIVO.hasSubjectArea, subject_uri))
                graph.add((subject_uri, RDF.type, SKOS.Concept))
                graph.add((subject_uri, RDFS.label, Literal(subject)))
        #Identifier
        if doi:
            graph.add((work_uri, BIBO.doi, Literal(doi)))
            #Also add as a website
            identifier_url = "http://dx.doi.org/%s" % doi
            vcard_uri = ns.D[to_hash_identifier("vcard", (identifier_url,))]
            graph.add((vcard_uri, RDF.type, VCARD.Kind))
            #Has contact info
            graph.add((work_uri, OBO.ARG_2000028, vcard_uri))
            #Url vcard
            vcard_url_uri = vcard_uri + "-url"
            graph.add((vcard_url_uri, RDF.type, VCARD.URL))
            graph.add((vcard_uri, VCARD.hasURL, vcard_url_uri))
            graph.add((vcard_url_uri, VCARD.url, Literal(identifier_url, datatype=XSD.anyURI)))

        #Publisher
        if publisher:
            publisher_uri = ns.D[to_hash_identifier(PREFIX_ORGANIZATION, (publisher,))]
            graph.add((publisher_uri, RDF.type, FOAF.Organization))
            graph.add((publisher_uri, RDFS.label, Literal(publisher)))
            graph.add((work_uri, VIVO.publisher, publisher_uri))

        #Volume
        if volume:
            graph.add((work_uri, BIBO.volume, Literal(volume)))
        #Number
        if number:
            graph.add((work_uri, BIBO.issue, Literal(number)))
        #Pages
        if start_page:
            graph.add((work_uri, BIBO.pageStart, Literal(start_page)))
        if end_page:
            graph.add((work_uri, BIBO.pageEnd, Literal(end_page)))

        #TODO: See #13 for mapping additional work types.
        if work_type == "JOURNAL_ARTICLE":
            #Type
            graph.add((work_uri, RDF.type, BIBO.AcademicArticle))
            #Journal
            if journal:
                journal_uri = ns.D[to_hash_identifier(PREFIX_JOURNAL, (BIBO.Journal, journal))]
                graph.add((journal_uri, RDF.type, BIBO.Journal))
                graph.add((journal_uri, RDFS.label, Literal(journal)))
                graph.add((work_uri, VIVO.hasPublicationVenue, journal_uri))

        elif work_type == "BOOK":
            ##Add triples
            #Type
            graph.add((work_uri, RDF.type, BIBO.Book))
        elif work_type == "DATA_SET":
            ##Add triples
            #Type
            graph.add((work_uri, RDF.type, VIVO.Dataset))


def fetch_crossref_doi(doi):
    #curl 'http://api.crossref.org/works/10.1177/1049732304268657' -L -i
    r = requests.get('http://api.crossref.org/works/%s' % doi)
    if r.status_code == 404:
        #Not a crossref DOI.
        return None
    if r:
        return r.json()["message"]
    else:
        raise Exception("Request to fetch DOI %s returned %s" % (doi, r.status_code))


def _parse_bibtex(work):
    bibtex = {}
    if work and work.get("work-citation", {}).get("work-citation-type") == "BIBTEX":
        citation = work["work-citation"]["citation"]
        #Need to add \n for bibtexparser to work
        curly_level = 0
        new_citation = ""
        for c in citation:
            if c == "{":
                curly_level += 1
            elif c == "}":
                curly_level -= 1
            new_citation += c
            if (curly_level == 1 and c == ",") or (curly_level == 0 and c == "}"):
                new_citation += "\n"
        parser = BibTexParser()
        parser.customization = bibtex_convert_to_unicode
        bibtex = bibtexparser.loads(new_citation, parser=parser).entries[0]
    return bibtex


def _get_crossref_title(crossref_record):
    if "title" in crossref_record and crossref_record["title"]:
        return crossref_record["title"][0]
    return None


def _get_orcid_title(work):
    return join_if_not_empty((work["work-title"]["title"]["value"],
                                   (work["work-title"].get("subtitle") or {}).get("value")), ": ")

def _get_publication_date(work):
    year = None
    month = None
    day = None
    publication_date = work.get("publication-date")
    if publication_date:
        year = publication_date["year"]["value"] if publication_date.get("year") else None
        month = publication_date["month"]["value"] if publication_date.get("month") else None
        day = publication_date["day"]["value"] if publication_date.get("day") else None
    return year, month, day


def _get_crossref_publication_date(doi_record):
    if "issued" in doi_record and "date-parts" in doi_record["issued"]:
        date_parts = doi_record["issued"]["date-parts"][0]
        return date_parts[0], date_parts[1] if len(date_parts) > 1 else None, date_parts[2] if len(date_parts) > 2 else None
    return None


def _get_work_identifiers(work):
    ids = {}
    external_identifiers = work.get("work-external-identifiers")
    if external_identifiers:
        for external_identifier in external_identifiers["work-external-identifier"]:
            ids[external_identifier["work-external-identifier-type"]] = \
                external_identifier["work-external-identifier-id"]["value"]
    return ids


def _get_crossref_authors(doi_record):
    authors = []
    for author in doi_record.get("author", []):
        authors.append((author["given"], author["family"]))
    return authors


def bibtex_convert_to_unicode(record):
    for val in record:
        if '\\' in record[val] or '{' in record[val]:
            for k, v in itertools.chain(unicode_to_crappy_latex1, unicode_to_latex):
                if v in record[val]:
                    record[val] = record[val].replace(v, k)
                #Try without space
                elif v.rstrip() in record[val]:
                    record[val] = record[val].replace(v.rstrip(), k)

        # If there is still very crappy items
        if '\\' in record[val]:
            for k, v in unicode_to_crappy_latex2:
                if v in record[val]:
                    parts = record[val].split(str(v))
                    for key, record[val] in enumerate(parts):
                        if key+1 < len(parts) and len(parts[key+1]) > 0:
                            # Change order to display accents
                            parts[key] = parts[key] + parts[key+1][0]
                            parts[key+1] = parts[key+1][1:]
                    record[val] = k.join(parts)

        #Also replace {\\&}
        if '{\\&}' in record[val]:
            record[val] = record[val].replace('{\\&}', '&')
    return record
