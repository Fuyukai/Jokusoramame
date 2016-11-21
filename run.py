from joku.manager import SingleLoopManager


def main():
    # Create a new thread Manager.
    m = SingleLoopManager()
    m.run()


if __name__ == "__main__":
    main()
