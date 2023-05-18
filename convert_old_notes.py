"""
Update obsidian literature notes to use a new citekey
"""
import re

from argparse import ArgumentParser
from glob import glob
from os import path
from difflib import SequenceMatcher

import bibtexparser
from LaTexHandler import LaTexAccents as accents

import pandas as pd

class LitNoteException(Exception):
    def __init__(self, filename, line, expected_line, line_number):
        self.message = f"Invalid note {filename}, found {line}, expected {expected_line} on {line_number}"
        super().__init__(self.message)

def read_file(filename):
    """
    open file, and parse the header
    """
    header_entry_exp = re.compile("(\w+): (.*)")
    line_num = 0
    data = {}
 
    with open(filename, "r") as f:
        first = f.readline().rstrip("\n")
        if first != "---":
            raise LitNoteException(filename, first, "---\n", line_num)
        while True:
            line = f.readline().rstrip("\n")
            line_num += 1
            if line == "---":
                return data
            match = header_entry_exp.match(line)
            if not match:
                raise LitNoteException(filename, line, header_entry_exp, line_num)
            data[match[1]] = match[2]

    return data

def gen_old_entries(vault_dir, verbose=False):
    """
    go through vault and find all lit notes
    """
    lit_files = glob(f"{vault_dir}/**/@*.md")
    header_data = {}

    for lit_file in lit_files:
        citekey = path.splitext(path.basename(lit_file))[0]
        
        if citekey in header_data:
            raise Exception(f"{citekey} duplicate entry")
        try:
            header_data[citekey] = read_file(lit_file)
        except LitNoteException as e:
            if verbose:
                print(e.message)
    return header_data

def parse_name(author):

    acc = accents.AccentConverter()
    auth_utf = acc.decode_Tex_Accents(author, utf8_or_ascii=1)

    token_match = re.compile("{.*}")

    if token_match.match(auth_utf.strip()):
        full_name = auth_utf.strip()
    elif "," in auth_utf:
        last, first = auth_utf.split(",")
        full_name = f"{first.strip()} {last.strip()}"
    else:
        full_name = auth_utf
    san_name = full_name.replace("{", "")
    san_name = san_name.replace("}","")
    san_name = san_name.rstrip()
    san_name = san_name.lstrip()

    return san_name

def sanitize_authors(author_list):

    acc = accents.AccentConverter()
    de_accented = acc.decode_Tex_Accents(author_list, utf8_or_ascii=1)
    return re.sub(r'\relax ', '', de_accented)

def parse_author_list(author_list):
    """
    Split the entries up, respecting { brackets
    """

    tokens = sanitize_authors(author_list).split()
    authors = []
 
    in_brackets = False
    curr_token = ""
 
    for token in tokens:
        if token == "and" and not in_brackets:
            authors.append(curr_token)
            curr_token = ""
        else:
            if token[0] == "{":
                in_brackets = True
            if re.match("^.?}[\.,]?$", token[-2:]):
                in_brackets = False
            curr_token += " "+token
    if in_brackets:
        raise Exception(f"Unenclosed brackets {author_list}")
    return authors

def compute_diff(authors_1, authors_2):
    return SequenceMatcher(lambda x: x in "{}", authors_1, authors_2).quick_ratio()

def map_entries(bib_filename, old_entries, verbose=False):
    """
    Try to match entries, first based on year,
    then based on authors, and then based on title

    return a mapping of (old_citekey, new_citekey) = (author_sim, title_sim)
    """

    with open(bib_filename, "r") as bib_file:
        bib = bibtexparser.load(bib_file) 

    values = {}

    for old_entry in old_entries:

        header_data = old_entries[old_entry]

        year = header_data["year"]
        authors = header_data["authors"]
        title = header_data["title"]

        for new_entry in bib.entries:
            if "year" not in new_entry or "author" not in new_entry or "title" not in new_entry:
                continue
            if new_entry["year"] != year:
                continue
            new_authors = [parse_name(author) for author in parse_author_list(new_entry["author"])]

            author_ratio = compute_diff(",".join(new_authors).replace(" ", "").lower(),
                                        authors.replace(" ", "").lower())

            title_ratio = compute_diff(new_entry["title"].lower(), title.lower())
            values[(old_entry, new_entry["ID"])] = (author_ratio, title_ratio)
 
    return values

if __name__ == "__main__":
    
    parser = ArgumentParser()
    parser.add_argument("vault_dir", help="directory with target vault")
    parser.add_argument("bib_file", help="new .bib file") 
    parser.add_argument("--verbose", action="store_true", default=False)

    args = parser.parse_args()
    
    old_entries = gen_old_entries(args.vault_dir, verbose=args.verbose) 
    candidates = map_entries(args.bib_file, old_entries, verbose=args.verbose)

    pd.DataFrame.from_dict(candidates, orient="index", columns=["author", "title"]).to_csv("./sample.csv")
