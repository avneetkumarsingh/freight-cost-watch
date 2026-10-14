"""Ask about the findings:  python ask.py "why did Chennai-Bangalore get pricier in March?"
(run `python run.py` first to create outputs/output.csv)"""
import sys

from costwatch import config, qa


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python ask.py "your question"')
    if not config.OUTPUT_CSV.exists():
        sys.exit("outputs/output.csv not found - run `python run.py` first")
    routes = ["Ahmedabad-Mumbai", "Chennai-Bangalore", "Delhi-Chennai", "Delhi-Jaipur",
              "Kolkata-Bhubaneswar", "Mumbai-Delhi", "Mumbai-Pune"]
    print(qa.answer(" ".join(sys.argv[1:]), qa.load_results(), routes))


if __name__ == "__main__":
    main()
