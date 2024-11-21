import requests
import json
import pdb
import math
from collections import defaultdict
import argparse
import datetime
import openai
import os
import random
MAX_PAPERS_TO_READ = 100

try:
    with open('request_cache.json', 'r') as f:
        request_cache = json.load(f)
except:
    request_cache = {}

def print_authors(authors):
    end = "...\n" if len(authors) > 3 else "\n"
    for i, author in enumerate(authors[:3]):
        if 'name' in author:
            if i == 0:
                print('\t\t\t\t', end="")
            print(f'{author["name"]}', end=", " if i < min(len(authors) - 1, 2) else end)

def get_paper_universe_with_multiplicity(paper_ids, ignore_super_cited, use_multiplicity=True):
    print(f"calling api for {len(paper_ids)} papers")
    r = requests.post(
        'https://api.semanticscholar.org/graph/v1/paper/batch',
        params={'fields': 'referenceCount,citationCount,influentialCitationCount,title,url,abstract,tldr,references,citations,paperId,authors'},
        json={"ids": paper_ids}
    )
    if r.status_code == 400:
        raise Exception("Bad request - received 400 status code from Semantic Scholar API")

    input_paper_titles = []
    for response in r.json():
        input_paper_titles.append(response['title'])
        request_cache[response['url']] = response

    with open('request_cache.json', 'w') as f:
        json.dump(request_cache, f)

    paper_universe_with_multiplicity = []

    for response in r.json():
        for ref in response['references']:
            paper_universe_with_multiplicity.append((ref['paperId'], ref['title']))
        if len(response['citations']) < ignore_super_cited:
            for citation in response['citations']:
                paper_universe_with_multiplicity.append((citation['paperId'], citation['title']))

    if not use_multiplicity:
        paper_universe_with_multiplicity = list(set(paper_universe_with_multiplicity))

    return paper_universe_with_multiplicity, input_paper_titles

def get_full_data_for_papers(paper_universe_with_multiplicity):
    r = requests.post(
        'https://api.semanticscholar.org/graph/v1/paper/batch',
        params={'fields': 'referenceCount,citationCount,influentialCitationCount,publicationDate,year,title,url,abstract,tldr,references,citations,paperId,authors'},
        json={"ids": [x[0] for x in paper_universe_with_multiplicity]}
    )
    return r.json()

def filter_papers_by_subfield(r_json, target_subfield, ranking_metric, max_papers=MAX_PAPERS_TO_READ):
    openai.api_key = os.environ['OPENAI_API_KEY']
    client = openai.OpenAI()
    filtered_r_json = []
    r_json.sort(key=lambda x: get_metric_val(x, ranking_metric) if x is not None else 0, reverse=True)
    og_len = len(r_json)
    r_json = r_json[:max_papers]
    print(f'Max num filter {og_len} -> {len(r_json)}')

    for response in r_json:
        if response is None:
            continue
        else:
            abstract = response['abstract']
            if abstract is not None:
                query = f'Determine if the following paper is in the {target_subfield} subfield using the abstract:\n{abstract}\n Is this paper in the {target_subfield} subfield? Answer yes or no.'
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {
                            "role": "user",
                            "content": query
                        }
                    ]
                )
                answer = completion.choices[0].message.content.lower()
                if 'yes' in answer:
                    filtered_r_json.append(response)
                    print(f'INCLUDE: {response["title"]}')
                else:
                    print(f'REMOVE FOR NON-RELEVANCE: {response["title"]}')
    return filtered_r_json

def get_metric_val(response, metric_type):
    if metric_type == 'citations':
        return response['citationCount']
    elif metric_type == 'influential_citations':
        return response['influentialCitationCount']
    elif metric_type == 'citations_per_day':
        publication_date = response['publicationDate']
        if publication_date:
            publication_date = datetime.datetime.strptime(publication_date, '%Y-%m-%d')
            days_since_publication = (datetime.datetime.now() - publication_date).days
        else:
            if response['year'] is not None:
                days_since_publication = (datetime.datetime.now() - datetime.datetime(response['year'], 1, 1)).days
            else:
                print(f'Warning: no publication date for {response["title"]}')
                days_since_publication = 365
        return response['citationCount'] / days_since_publication

def get_paper_citation_counts(r_json, ranking_metric):
    paper_citation_counts = defaultdict(int)
    title_metadata_map = {}
    for response in r_json:
        if response is None:
            pass
        else:
            if response['title'] is not None:
                title_metadata_map[response['title']] = (response['authors'], response['publicationDate'])
                paper_citation_counts[response['title']] += get_metric_val(response, ranking_metric)
    
    return paper_citation_counts, title_metadata_map

def score_function(ranking_metric_value):
    return math.log(ranking_metric_value + 1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze papers from Semantic Scholar')
    parser.add_argument('--paper_ids', nargs='+', help='List of paper IDs to analyze', required=True)
    parser.add_argument('--completed_paper_list', help='Path to a list of completed papers', required=False, default=None)
    parser.add_argument('--interactive_mode', action='store_true', help='Whether to run in interactive mode', required=False, default=False)
    parser.add_argument('--ranking_metric', type=str, choices=['citations', 'influential_citations', 'citations_per_day'], 
                        help='Metric to use for ranking papers', required=False, default='citations')
    parser.add_argument('--max_num_papers_to_read', type=int, help='Number of papers to read', required=False, default=None)
    parser.add_argument('--paper_description_type', choices=['None', 'abstract', 'tldr'], help='Type of paper description to use', required=False, default='tldr')
    parser.add_argument('--target_subfield_filter', help='Target subfield to read papers in', required=False, default=None)
    parser.add_argument('--k_steps', type=int, help='Number of steps to take in the paper graph', required=False, default=1)
    parser.add_argument('--ignore_super_cited', type=int, help='Ignore papers with more than this number of citations when searching for citations', required=False, default=500)
    args = parser.parse_args()

    paper_ids = args.paper_ids

    seen_papers = set()

    if args.k_steps > 1:
        print("Warning: k_steps > 1 is experimental. It seems to work better to use k=1, and input a larger number of papers.")

    for k in range(args.k_steps):
        print(f'Step {k}')
        if len(paper_ids) == 0:
            print('No more papers, exiting')
            break
        paper_universe_with_multiplicity, input_paper_titles = get_paper_universe_with_multiplicity(paper_ids, args.ignore_super_cited, use_multiplicity=False)
        for title in input_paper_titles:
            seen_papers.add(title)
        print(f'Got {len(paper_universe_with_multiplicity)} papers for filtering/ranking')
        if len(paper_universe_with_multiplicity) > 500:
            print('Warning: more than 500 papers. Sampling to 500')
            paper_universe_with_multiplicity = random.sample(paper_universe_with_multiplicity, 500)
        r_json = get_full_data_for_papers(paper_universe_with_multiplicity)

        if args.target_subfield_filter is not None:
            max_papers = min(args.max_num_papers_to_read, MAX_PAPERS_TO_READ) if args.max_num_papers_to_read is not None else MAX_PAPERS_TO_READ
            r_json = filter_papers_by_subfield(r_json, args.target_subfield_filter, args.ranking_metric, max_papers=max_papers)
            print(f'Filtered to {len(r_json)} papers')


        paper_ids = [x['paperId'] for x in r_json if x['title'] not in seen_papers]
    paper_citation_counts, title_metadata_map = get_paper_citation_counts(r_json, args.ranking_metric)
    print(f'Got {len(paper_citation_counts)} papers with citation metric {args.ranking_metric}')


    completed_papers = None
    if args.completed_paper_list is not None:
        with open(args.completed_paper_list, 'r') as f:
            completed_papers = set(f.read().splitlines())

    ordered_paper_citation_counts = sorted(paper_citation_counts.items(), key=lambda x: x[1], reverse=True)

    read_score = 0
    total_possible_score = 0

    if args.interactive_mode:
        assert args.completed_paper_list is not None, 'Interactive mode requires a completed paper list'

    to_read = []
    print(f'Publish Date\t{args.ranking_metric:10}\tPaper Title')
    for paper, count in ordered_paper_citation_counts:
        paper_score = score_function(count)
        total_possible_score += paper_score
        if completed_papers and paper in completed_papers:
            read_score += paper_score
        else:
            print('')
            authors, publish_date = title_metadata_map[paper]
            print(f'{publish_date}\t{paper_score:<5.2f}\t{paper}')
            print_authors(authors)
            has_read = False
            if args.interactive_mode:
                has_read_input = input('\tHave you read this paper? (y/n)\n')
                if has_read_input.lower() == 'y':
                    read_score += paper_score
                    completed_papers.add(paper)
                    has_read = True
                if has_read_input.lower() == 'q':
                    break
                if has_read_input.lower() == 'c':
                    args.interactive_mode = False
            if not has_read:
                to_read.append((count, paper))
        if args.max_num_papers_to_read is not None:
            if len(to_read) >= args.max_num_papers_to_read:
                break
    if args.interactive_mode:
        with open(args.completed_paper_list, 'w') as f:
            for paper in completed_papers:
                f.write(f'{paper}\n')
                
    if completed_papers is not None:
        print(f'Total possible score: {total_possible_score}')
        print(f'Read score: {read_score}')
        print(f'Fraction of possible score read: {read_score / total_possible_score}')
