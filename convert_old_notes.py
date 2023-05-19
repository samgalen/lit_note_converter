"""
Update obsidian literature notes to use a new citekey
"""
import re
import json
import shutil

from argparse import ArgumentParser
from glob import glob
from os import path

import bibtexparser
import editdistance

import pandas as pd

from tqdm import tqdm

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

def check_uids(old_cite, new_cite):
    """
    if both have a year, and issn, or doi field, do a quick check to ensure compatibility 
    
    return true if match
    """

    if "doi" in old_cite and "doi" in new_cite:
        return old_cite["doi"] == new_cite["doi"]
    if "issn" in old_cite and "issn" in new_cite:
        return old_cite["issn"] == new_cite["issn"]
    if "year" in old_cite and "year" in new_cite:
        if "month" in old_cite and "month" in new_cite:
            return (old_cite["year"] == new_cite["year"]) and (old_cite["month"] == new_cite["month"])
        return old_cite["year"] == new_cite["year"] 
    if "doi" in old_cite and "doi" not in new_cite:
        return False

    return True
def map_bibs(cite_list, bib_file_1, bib_file_2, verbose):
    """
    Given list of citations (lit note titles) 
    try to match cite_key from bib_file_1 to citekey in bib_file_2
    """

    with open(bib_file_1, "r") as f:
        bib_1 = bibtexparser.load(f)
    with open(bib_file_2, "r") as f:
        bib_2 = bibtexparser.load(f)

    index = pd.MultiIndex.from_product([cite_list, bib_2.entries_dict.keys()], 
                                        names = ["old", "new"])
    comp_data = pd.DataFrame(index=index, columns = ["sim", "n_comp", "n_fields_old", "n_fields_new"])

    for citekey in tqdm(cite_list):
        if citekey not in bib_1.entries_dict:
            if verbose:
                print(f"{citekey} is not in {bib_file_1}")
            continue
        old_cite = bib_1.entries_dict[citekey]
        for new_cite in bib_2.entries:

            sim = 0.0
            n_comp = 0.0

            if not check_uids(old_cite, new_cite):
                continue 

            for key in old_cite:
                if key not in new_cite:
                    continue
                sim += editdistance.eval(old_cite[key], new_cite[key])
                n_comp += 1

            comp_data.loc[(citekey, new_cite["ID"]), "sim"] = sim
            comp_data.loc[(citekey, new_cite["ID"]), "n_comp"] = n_comp
            comp_data.loc[(citekey, new_cite["ID"]), "n_fields_old"] = len(old_cite)
            comp_data.loc[(citekey, new_cite["ID"]), "n_fields_new"] = len(new_cite)                             

    if verbose:
        print(f"Performed {len(comp_data.dropna())}/{len(index)} matchings")

    return comp_data.dropna() # nas are where comparison did not work

def handle_note(note_file, citekey_map, verbose, dry_run):

    print_output = dry_run or verbose
    link_expr = re.compile(r'\[\[([^\]]*)\]\]')
 
    with open(note_file, "r") as f:
        contents = f.read()
    new_contents = contents[:]
    citations = []

    # we will modify by going from back to front
    # to avoid indexing issues

    for match in link_expr.finditer(contents):
        if match[1] in citekey_map:
            citations = [match] + citations
    for old_cite in citations:

        new_citation = citekey_map[old_cite[1]]
        old_lb, old_ub = old_cite.span()
        new_contents = "".join([new_contents[:old_lb+2], new_citation, new_contents[old_ub-2:]])

        if print_output:
            ub = max(old_ub, old_lb+len(new_citation)+4)
            print(f"{note_file} {contents[old_lb:old_ub]} -> {new_contents[old_lb:ub]}")
    file_base = path.splitext(path.basename(note_file))[0]
    
    if file_base in citekey_map:
        new_name = f"{citekey_map[file_base]}.md"
        new_file = path.join(path.dirname(note_file), new_name)
        
        if print_output:
            print(f"mv {note_file} -> {new_file}")
    else:
        new_file = note_file
    
    if not dry_run:
        if note_file != new_file:
            shutil.move(note_file, new_file)
        with open(new_file, "w") as f:
            f.write(new_contents)
if __name__ == "__main__":
    
    parser = ArgumentParser()
    parser.add_argument("vault_dir", help="directory with target vault")
    parser.add_argument("old_bib", help="old .bib file")
    parser.add_argument("new_bib", help="new .bib file") 
    parser.add_argument("--candidates-only", action="store_true", 
            help="Automatically match based on field edit distance, if false, outputs a csv with distances")
    parser.add_argument("--update-vault", action="store_true", help="using matches.json, update the target vault dir")
    parser.add_argument("--dry-run", action="store_true", help="output list of vault modifications, but do not apply them")
    parser.add_argument("--verbose", action="store_true", default=False)
    
    args = parser.parse_args()
  
    if not args.update_vault: 
     
        old_entries = gen_old_entries(args.vault_dir, verbose=args.verbose) 
        cite_list = [ck[1:] for ck in old_entries]
        bib_dists = map_bibs(cite_list, args.old_bib, args.new_bib, args.verbose)
 
        if args.candidates_only: 
          bib_dists.to_csv("./bib_distances.csv") 
        else: 
            avg_dists = bib_dists["sim"]/bib_dists["n_comp"]
            min_idx = avg_dists.astype("float64").groupby("old").idxmin()
        
            cite_map = {k : v for k,v in min_idx.values}

            with open("matches.json", "w") as f:
                json.dump(cite_map, f, indent="\t")
    else:
        with open("matches.json", "r") as f:
            citekey_map = json.load(f)

        citekey_map = {"@" + k : "@" + v for k,v in citekey_map.items()}

        vault_files = glob(f"{args.vault_dir}/**/*.md")

        for note_file in vault_files:
            handle_note(note_file, citekey_map, args.verbose, args.dry_run)
