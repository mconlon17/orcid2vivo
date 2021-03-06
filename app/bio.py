from vivo_namespace import VIVO
from rdflib import RDFS, RDF, Literal, XSD
from utility import join_if_not_empty
from vivo_namespace import VCARD, OBO, FOAF


def crosswalk_bio(orcid_profile, person_uri, graph, skip_person=False, person_class=FOAF.Person,
                  existing_vcard_uri=None, skip_name_vcard=False):

    #Get names (for person and name vcard)
    person_details = orcid_profile["orcid-profile"]["orcid-bio"].get("personal-details", {})
    given_names = person_details.get("given-names", {}).get("value")
    family_name = person_details.get("family-name", {}).get("value")
    full_name = join_if_not_empty((given_names, family_name))

    #Following is non-vcard bio information

    #If skip_person, then don't create person and add names
    if not skip_person:
        #Add person
        graph.add((person_uri, RDF.type, person_class))
        graph.add((person_uri, RDFS.label, Literal(full_name)))

    #Biography
    biography = (orcid_profile["orcid-profile"]["orcid-bio"].get("biography") or {}).get("value")
    if biography:
        graph.add((person_uri, VIVO.overview, Literal(biography)))

    #Other identifiers
    #Default VIVO-ISF only supports a limited number of identifier types.
    external_identifiers = \
        (orcid_profile["orcid-profile"]["orcid-bio"].get("external-identifiers", {}) or {}).get("external-identifier", [])
    for external_identifier in external_identifiers:
        #Scopus ID
        if external_identifier["external-id-common-name"]["value"] == "Scopus Author ID":
            graph.add((person_uri, VIVO.scopusId, Literal(external_identifier["external-id-reference"]["value"])))

        #ISI Research ID
        if external_identifier["external-id-common-name"]["value"] == "ResearcherID":
            graph.add((person_uri, VIVO.researcherId, Literal(external_identifier["external-id-reference"]["value"])))

    #Keywords
    keywords =  \
        (orcid_profile["orcid-profile"]["orcid-bio"].get("keywords", {}) or {}).get("keyword", [])
    for keyword in keywords:
        graph.add((person_uri, VIVO.freetextKeyword, Literal(keyword["value"])))

    #Following is vcard bio information

    #Add main vcard
    vcard_uri = existing_vcard_uri or person_uri + "-vcard"
    #Will only add vcard if there is a child vcard
    add_main_vcard = False

    if not skip_name_vcard and (given_names or family_name):
        #Name vcard
        vcard_name_uri = person_uri + "-vcard-name"
        graph.add((vcard_name_uri, RDF.type, VCARD.Name))
        graph.add((vcard_uri, VCARD.hasName, vcard_name_uri))
        if given_names:
            graph.add((vcard_name_uri, VCARD.givenName, Literal(given_names)))
        if family_name:
            graph.add((vcard_name_uri, VCARD.familyName, Literal(family_name)))
        add_main_vcard = True

    #Websites
    researcher_urls = \
        (orcid_profile["orcid-profile"]["orcid-bio"].get("researcher-urls", {}) or {}).get("researcher-url", [])
    for index, researcher_url in enumerate(researcher_urls):
        url = researcher_url["url"]["value"]
        url_name = (researcher_url["url-name"] or {}).get("value")
        vcard_website_uri = person_uri + "-vcard-website" + str(index)
        graph.add((vcard_website_uri, RDF.type, VCARD.URL))
        graph.add((vcard_uri, VCARD.hasURL, vcard_website_uri))
        graph.add((vcard_website_uri, VCARD.url, Literal(url, datatype=XSD.anyURI)))
        if url_name:
            graph.add((vcard_website_uri, RDFS.label, Literal(url_name)))

    if add_main_vcard and not existing_vcard_uri:
        graph.add((vcard_uri, RDF.type, VCARD.Individual))
        #Contact info for
        graph.add((vcard_uri, OBO.ARG_2000029, person_uri))
