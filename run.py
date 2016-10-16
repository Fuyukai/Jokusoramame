from joku.threadmanager import Manager


def main():
    # Create a new thread Manager.
    m = Manager()
    m.start_all()


if __name__ == "__main__":
    main()
