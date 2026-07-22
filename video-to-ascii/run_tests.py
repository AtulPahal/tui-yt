import unittest
import sys

def main():
    print("Discovering and running tests...")
    loader = unittest.TestLoader()
    suite = loader.discover('tests', pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        print("\nSome tests failed!")
        sys.exit(1)
    else:
        print("\nAll tests passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
