"""Explicitly activated queue worker; setup exits before any provider write."""
import json
from .runtime import publish_due


def main():
    print(json.dumps(publish_due()))


if __name__=='__main__':main()
