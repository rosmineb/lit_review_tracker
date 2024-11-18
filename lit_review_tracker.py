import requests
import json
import pdb
import math
from collections import defaultdict
import argparse
import datetime
import openai
import os

try:
    with open('request_cache.json', 'r') as f:
        request_cache = json.load(f)
except:
    request_cache = {}

try:
    with open('finished_papers.csv', 'r') as f:
        finished_papers = set(f.read().splitlines())
except:
    finished_papers = set()

    def get_paper_universe_with_multiplicity(args):
        r = requests.post(
            'https://api.semanticscholar.org/graph/v1/paper/batch',
            params={'fields': 'referenceCount,citationCount,influentialCitationCount,title,url,abstract,tldr,references,citations'},
            json={"ids": args.paper_ids}
        )

        for response in r.json():
            request_cache[response['url']] = response

        with open('request_cache.json', 'w') as f:
            json.dump(request_cache, f)

        paper_universe_with_multiplicity = []

        for response in r.json():
            for ref in response['references']:
                paper_universe_with_multiplicity.append((ref['paperId'], ref['title']))
            for citation in response['citations']:
                paper_universe_with_multiplicity.append((citation['paperId'], ref['title']))

        return paper_universe_with_multiplicity

    def get_full_data_for_papers(paper_universe_with_multiplicity):
        r = requests.post(
            'https://api.semanticscholar.org/graph/v1/paper/batch',
            params={'fields': 'referenceCount,citationCount,influentialCitationCount,publicationDate,year,title,url,abstract,tldr,references,citations'},
            json={"ids": [x[0] for x in paper_universe_with_multiplicity]}
        )
        return r.json()

    def filter_papers_by_subfield(r_json, target_subfield):
        openai.api_key = os.environ['OPENAI_API_KEY']
        client = openai.OpenAI()
        filtered_r_json = []
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
                        print(f'INCLUDE {response["title"]}')
                    else:
                        print(f'DELETE {response["title"]}')
        return filtered_r_json


    def get_paper_citation_counts(r_json, ranking_metric):
        paper_citation_counts = defaultdict(int)
        for response in r_json:
            if response is None:
                pass
            else:
                if response['title'] is not None:
                    if ranking_metric == 'citations':
                        paper_citation_counts[response['title']] += response['citationCount']
                    elif ranking_metric == 'influential_citations':
                        paper_citation_counts[response['title']] += response['influentialCitationCount']
                    elif ranking_metric == 'citations_per_day':
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
                        paper_citation_counts[response['title']] += response['citationCount'] / days_since_publication
        
        return paper_citation_counts

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze papers from Semantic Scholar')
    parser.add_argument('--paper_ids', nargs='+', help='List of paper IDs to analyze', required=True)
    parser.add_argument('--completed_paper_list', help='Path to a list of completed papers', required=False, default=None)
    parser.add_argument('--interactive_mode', action='store_true', help='Whether to run in interactive mode', required=False, default=False)
    parser.add_argument('--ranking_metric', type=str, choices=['citations', 'influential_citations', 'citations_per_day'], 
                        help='Metric to use for ranking papers', required=False, default='citations')
    parser.add_argument('--num_papers_to_read', type=int, help='Number of papers to read', required=False, default=None)
    parser.add_argument('--paper_description_type', choices=['None', 'abstract', 'tldr'], help='Type of paper description to use', required=False, default='tldr')
    parser.add_argument('--target_subfield_filter', help='Target subfield to read papers in', required=False, default=None)
    args = parser.parse_args()


    value_metric = 'influentialCitationCount' #'citationCount'
    # ids = ["ARXIV:2409.11321"]

    paper_universe_with_multiplicity = get_paper_universe_with_multiplicity(args)
    r_json = get_full_data_for_papers(paper_universe_with_multiplicity)
    if args.target_subfield_filter is not None:
        if args.num_papers_to_read is not None:
            r_json = r_json[:args.num_papers_to_read]
        r_json = filter_papers_by_subfield(r_json, args.target_subfield_filter)
    paper_citation_counts = get_paper_citation_counts(r_json, args.ranking_metric)


    if args.completed_paper_list is not None:
        with open(args.completed_paper_list, 'r') as f:
            completed_papers = set(f.read().splitlines())

    ordered_paper_citation_counts = sorted(paper_citation_counts.items(), key=lambda x: x[1], reverse=True)

    read_score = 0
    total_possible_score = 0

    if args.interactive_mode:
        assert args.completed_paper_list is not None, 'Interactive mode requires a completed paper list'

    to_read = []
    print(f'{args.ranking_metric:10}\tPaper Title')
    for paper, count in ordered_paper_citation_counts:
        total_possible_score += math.log(count + 1) + 1
        if paper in completed_papers:
            read_score += math.log(count + 1) + 1
        else:
            print('')
            print(f'{math.log(count + 1) + 1:<5.2f}\t{paper}')
            has_read = False
            if args.interactive_mode:
                has_read_input = input('\tHave you read this paper? (y/n)\n')
                if has_read_input.lower() == 'y':
                    read_score += math.log(count + 1) + 1
                    completed_papers.add(paper)
                    has_read = True
                if has_read_input.lower() == 'q':
                    break
                if has_read_input.lower() == 'c':
                    args.interactive_mode = False
            if not has_read:
                to_read.append((count, paper))
        if args.num_papers_to_read is not None:
            if len(to_read) >= args.num_papers_to_read:
                break
    if args.interactive_mode:
        with open(args.completed_paper_list, 'w') as f:
            for paper in completed_papers:
                f.write(f'{paper}\n')
                
    print(f'Total possible score: {total_possible_score}')
    print(f'Read score: {read_score}')
    print(f'Fraction of possible score read: {read_score / total_possible_score}')
