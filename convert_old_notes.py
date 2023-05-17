"""
Update obsidian literature notes to use a new citekey
"""
import re

from argparse import ArgumentParser
from glob import glob
from os import path

import bibtexparser

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

def map_entries(bib_filename, old_entries):
    """
    Try to match entries, first based on year,
    then based on authors, and then based on title
    """

    with open(bib_filename, "r") as bib_file:
        bib = bibtexparser.load(bib_file) 

    candidates = {old_entry : [] for old_entry in old_entries} # map old citekey -> [new citekeys]

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
            new_authors = []
            for author in new_entry["author"].split("and"):
                if len(author.split()) == 2:
                    if "," in author:
                        last, first = author.split(",")
                    else:
                        first, last = author.split()
                    first.replace("{","").strip()
                    last.replace("{","").strip()
                    new_authors.append(f"{first} {last}")
                else:
                    new_authors.append(f"{author.replace('{','').replace('}','').strip()}")
            if ",".join(new_authors) != authors:
                print(f"""new_authors: {",".join(new_authors)}, old_authors: {authors}""")
                continue
            title_disc = title.split()
            title_dist = sum([t in new_entry["title"] for t in title_disc])/float(len(title_disc))

            if title_dist < 0.8:
                continue
            candidates[old_entry].append(new_entry["ID"])
    return candidates

if __name__ == "__main__":
    
    parser = ArgumentParser()
    parser.add_argument("vault_dir", help="directory with target vault")
    parser.add_argument("bib_file", help="new .bib file") 
    parser.add_argument("--verbose", action="store_true", default=False)

    args = parser.parse_args()
    
    old_entries = gen_old_entries(args.vault_dir, verbose=args.verbose) 
    candidates = map_entries(args.bib_file, old_entries)
  
    for c in candidates:
        if len(candidates[c]) != 1:
            print(c, candidates[c])
    
