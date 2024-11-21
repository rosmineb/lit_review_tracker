This is a tool for literature review that 1. helps find useful papers and 2. quantifies how much of an expert you are in a particular subfield (so you know once you've read enough).

Here's an example usage:

```
python lit_review_tracker.py --paper_ids "ARXIV:2409.11321" "ARXIV:1802.09568" "ARXIV:1703.04782" --ranking_metric citations_per_day --target_subfield_filter Optimizers --k_steps 1 --max_num_papers_to_read 100
```

You need to seed it with several papers that you want to use as a starting point. This uses semantic scholar format for paper ids, so if there is not an arxiv version of the paper, you can use the ID from the semantic scholar page, e.g. 
Attention Is All You Need -> https://www.semanticscholar.org/paper/Attention-is-All-you-Need-Vaswani-Shazeer/204e3073870fae3d05bcbc2f6a8e263d9b72e776 -> ID is 204e3073870fae3d05bcbc2f6a8e263d9b72e776

## Requirements

This calls the OpenAI API to filter the papers to the relevant subfield. You will need to have a `OPENAI_API_KEY` defined in your environment. See https://platform.openai.com/docs/quickstart for instructions.

## Tracking Papers you've read

You can use the flag `--completed_paper_list /path/to/file` to input a list of papers you've read (each line of this file should be the title of one paper). These papers will be filtered out of suggested results, and at the end it will print a score.

## Options

You can change the order of the papers using `--ranking_metric`, it can be `citations_per_day` (default), `influential_citations`, or `influential_citations`

## Ranking/Scoring

First, choose the ranking metric (see options above). 

The score of each paper is log(ranking_metric + 1)

The +1 is to prevent log(0)

## Sample output

python lit_review_tracker.py --paper_ids "ARXIV:2409.11321" "ARXIV:1802.09568" "ARXIV:1703.04782" --ranking_metric citations_per_day --target_subfield_filter Optimizers --k_steps 1 --max_num_papers_to_read 100 --completed_paper_list empty_file                                           
Step 0
calling api for 3 papers
Got 482 papers for filtering/ranking
Max num filter 482 -> 100
REMOVE FOR NON-RELEVANCE: Attention is All you Need
INCLUDE: Adam: A Method for Stochastic Optimization
REMOVE FOR NON-RELEVANCE: Very Deep Convolutional Networks for Large-Scale Image Recognition
(list of papers in the reference/citation graph, and if they match the subfield or not)
REMOVE FOR NON-RELEVANCE: On the Factory Floor: ML Engineering for Industrial-Scale Ads Recommendation Models
REMOVE FOR NON-RELEVANCE: Bayesian Low Rank Tensor Ring for Image Recovery
Filtered to 57 papers
Got 57 papers with citation metric citations_per_day
Publish Date	citations_per_day	Paper Title

2014-12-22	3.69 	Adam: A Method for Stochastic Optimization
				Diederik P. Kingma, Jimmy Ba

2011-02-01	1.10 	Adaptive Subgradient Methods for Online Learning and Stochastic Optimization
				John C. Duchi, Elad Hazan, Y. Singer



2015-08-12	0.04 	Convergence rates of sub-sampled Newton methods
				Murat A. Erdogdu, A. Montanari

2018-11-29	0.04 	Large-Scale Distributed Second-Order Optimization Using Kronecker-Factored Approximate Curvature for Deep Convolutional Neural Networks
				Kazuki Osawa, Yohei Tsuji, Yuichiro Ueno...    
Total possible score: 14.206430807201532
Read score: 0.0
Fraction of possible score read: 0.0
```
## How it works

It works by running BFS on the paper reference/citation graph (edges are both papers that a paper cites, and the papers that cite it) to find candidate papers. It then calls `gpt-4o-mini` to ask if the abstract of the paper matches the specified subfield.

## Cost to run

I ran this script many times while developing it. All the calls to `gpt-4o-mini` combined cost a total of $0.08. Each run should cost less than a cent. It will be more if you set both `--max_num_papers_to_read` and `--k_steps` to be large, so do that at your own risk. 

## Warning/Limitations: 
- I quickly hacked this together. There will be bugs and missing features. The algorithm for finding the papers is decent, but could be better. If there is enough interest, I will make improvements. 
- Paper Ranking is based on citation counts. Even when normalizing by time with citations_per_day, this will miss papers that are too recent to have any citations. 
- If you don't get enough results, try increasing `--max_num_papers_to_read`
- For each input paper, the algorithm looks at both references, and papers that cite it. For popular papers there could be tens of thousands of papers citing it. Including these reduces the quality of the results, so there is a 
 `--ignore_super_cited` flag that takes an integer value (default 500), and ignores the citations of a paper if it has more than that value. If you are specifically looking for paperes in a subfield defined by a single paper (e.g. you want to look at all variants of LoRA)
 then you should use this script with that single paper as input, use `--k_steps 1`, and set `--ignore_super_cited` to be very large, larger than the number of citations for that paper.
