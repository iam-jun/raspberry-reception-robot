#!/usr/bin/env python3
import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask the RAG service a question.")
    parser.add_argument("--question", required=True, help="Question to answer.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # TODO: Retrieve relevant chunks from the vector store.
    # TODO: Generate an answer with the selected local or remote LLM.
    print(f"Placeholder RAG answer for: {args.question}")


if __name__ == "__main__":
    main()

