from flask import Flask, request, jsonify, g
import os
import logging
from logging.handlers import RotatingFileHandler
import time

app = Flask(__name__)

Genere = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
books = []
requestCounter = 0

print("working")
def createLogFolder():
    logDir = 'logs'
    currentPath = os.path.dirname(os.path.abspath(__file__))
    fullPath = os.path.join(currentPath, logDir)
    if not os.path.exists(fullPath):
        os.makedirs(fullPath)
        print(f"Created log directory at {fullPath}")
    else:
        print(f"Log directory already exists at {fullPath}")

class CustomFormatter(logging.Formatter):
    def format(self, record):
        ct = time.localtime(record.created)
        ms = int(record.created % 1 * 1000)
        s = time.strftime('%d-%m-%Y %H:%M:%S', ct)
        record.customTime = f"{s}.{ms:03d}"
        record.requestNumber = getattr(record, 'requestNumber', 'N/A')
        return super(CustomFormatter, self).format(record)

def setupRequestLogger():
    loggerName = 'request-logger'  # Define a specific name for the logger
    logDir = 'logs'
    currentPath = os.path.dirname(os.path.abspath(__file__))
    fullPath = os.path.join(currentPath, logDir, 'requests.log')

    requestLogger = logging.getLogger(loggerName)  # Create a named logger
    requestLogger.setLevel(logging.DEBUG)  # Set the logger's default level to INFO

    fileHandler = RotatingFileHandler(fullPath, maxBytes=10240, backupCount=5)
    fileHandler.setLevel(logging.DEBUG)
    formatter = CustomFormatter('%(customTime)s %(levelname)s: %(message)s | request #%(requestNumber)s')
    fileHandler.setFormatter(formatter)
    requestLogger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logging.INFO)
    consoleHandler.setFormatter(formatter)
    requestLogger.addHandler(consoleHandler)


def setupBooksLogger():
    logDir = 'logs'
    currentPath = os.path.dirname(os.path.abspath(__file__))
    booksLogPath = os.path.join(currentPath, logDir, 'books.log')

    # Create a logger for the books
    booksLogger = logging.getLogger('books-logger')
    booksLogger.setLevel(logging.DEBUG)  # Default level set to INFO

    # Set up file handler
    fileHandler = RotatingFileHandler(booksLogPath, maxBytes=10240, backupCount=5)
    fileHandler.setLevel(logging.INFO)  # File handler level set to INFO
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s' , datefmt='%d-%m-%Y %H:%M:%S')
    fileHandler.setFormatter(formatter)
    booksLogger.addHandler(fileHandler)

@app.before_request
def startRequest():
    requestLogger = logging.getLogger('request-logger')
    global requestCounter
    requestCounter += 1
    g.requestNumber = requestCounter
    g.startTime = time.time()
    requestLogger.info(f"Incoming request | #{g.requestNumber} | resource: {request.path} | HTTP Verb {request.method.upper()}",
                    extra={'requestNumber': g.requestNumber})


@app.after_request
def logRequest(response):
    requestLogger = logging.getLogger('request-logger')
    requestDuration = round((time.time() - g.startTime) * 1000)  # Duration in milliseconds
    requestLogger.info(f"request #{g.requestNumber} duration: {requestDuration}ms",
                     extra={'requestNumber': g.requestNumber})
    return response


@app.route('/books/health', methods=['GET'])
def health_check():
    return "OK", 200


@app.route('/book', methods=['POST'])
def assignNewBook():
    booksLogger = logging.getLogger('books-logger')
    data = request.get_json()
    validRequst = True
    if CheckBookName(data['title']) != True:
        Errormessage = f"Error: Book with the title [{data['title'].strip()}] already exists in the system"
        validRequst = False

    if CheckBookPrice(int(data['price'])) != True:
        Errormessage = f"Error: Can’t create new Book with negative price"
        validRequst = False
    if checkYear(int(data['year'])) != True:
        Errormessage = f"Error: Can’t create new Book that its year {data['year']} is not in the accepted range [1940 -> 2100]"
        validRequst = False
    if validRequst == True:
        books.append(
            {
                "id": books.__len__() + 1,
                "title": data['title'].strip(),
                "author": data['author'].strip(),
                "year": int(data['year']),
                "price": int(data['price']),
                "genres": [genre.strip() for genre in data['genres']]
            })
        booksLogger.info(f"Creating new Book with Title [{data['title'].strip()}] | request #{g.requestNumber} ")
        booksLogger.debug(
            f"Currently there are {len(books) - 1} Books in the system. New Book will be assigned with id {books.__len__()} | request #{g.requestNumber} ")
        return "OK", 200

    else:
        booksLogger.error(f"{Errormessage}| request #{g.requestNumber} ")
        return jsonify({"errorMessage": Errormessage}), 409


@app.route('/books/total', methods=['GET'])
def getNumberOfBooks():
    booksLogger = logging.getLogger('books-logger')
    genres = request.args.get('genres')

    if genres:
        genre_list = genres.split(',')
        valid_genres = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
        if not all(genre in valid_genres for genre in genre_list):
            booksLogger.error(f"Invalid genre specified | request #{g.requestNumber} ")
            return jsonify({"errorMessage": "Invalid genre specified"}), 400

    filtered_books = filterbooks(request)
    booksLogger.info(
        f"Total Books found for requested filters is {len(filtered_books)} | request #{g.requestNumber} ")
    return jsonify({"result": len(filtered_books)}), 200


@app.route('/book', methods=['Get'])
def getBookById():
    booksLogger = logging.getLogger('books-logger')
    id = int(request.args.get('id'))
    book = next((book for book in books if book['id'] == id), None)
    if book is not None:
        booksLogger.debug(f"Fetching book id {id} details | request #{g.requestNumber} ")
        return jsonify({"result": book}), 200


    else:
        # If no book found, return a 404 Not Found response
        booksLogger.error(f"Error: no such Book with id {id} | request #{g.requestNumber} ")
        return jsonify({"errorMessage": f"Error: no such Book with id {id}"}), 404


@app.route('/book', methods=['PUT'])
def updateBookPrice():
    booksLogger = logging.getLogger('books-logger')
    validRequst = True
    id = int(request.args.get('id'))
    newPrice = int(request.args.get('price'))

    if CheckBookPrice(newPrice) != True:
        Errormessage = f"Error: price update for book {id} must be a positive integer"
        errorCode = 409
        validRequst = False

    book = next((book for book in books if book['id'] == id), None)
    if book is None:
        Errormessage = f"Error: no such Book with id {id}"
        errorCode = 404
        validRequst = False

    if validRequst == False:
        booksLogger.error(f"{Errormessage} | request #{g.requestNumber}")
        return jsonify({"errorMessage": Errormessage}), errorCode

    else:
        oldPrice = book["price"]
        book["price"] = newPrice
        title=book["title"]
        booksLogger.info(f"Update Book id [{id}] price to {newPrice} | request #{g.requestNumber} ")
        booksLogger.debug( f"Book [{title}] price change: {oldPrice} --> {newPrice} | request #{g.requestNumber} ")
        return jsonify({"result": oldPrice}), 200


@app.route('/book', methods=['DELETE'])
def removeBook():
    booksLogger = logging.getLogger('books-logger')
    BookToRemove = None
    id = int(request.args.get('id'))
    for book in books:
        if book['id'] == id:
            BookToRemove = book
            break

    if BookToRemove:
        title=BookToRemove["title"]
        books.remove(BookToRemove)
        booksLogger.info(f"Removing book [{title}] | request #{g.requestNumber}  ")
        booksLogger.debug(f"After removing book [{title}] id: [{id}] there are {len(books)} books in the system | request #{g.requestNumber} ")
        return jsonify({"result": books.__len__()}), 200


    else:
        booksLogger.error(f"Error: no such Book with id {id} | request #{g.requestNumber} ")
        return jsonify({"errorMessage": f"Error: no such Book with id {id}"}), 404


@app.route('/books', methods=['GET'])
def getBooks():
    booksLogger = logging.getLogger('books-logger')
    genres = request.args.get('genres')

    if genres:
        genre_list = genres.split(',')
        valid_genres = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
        if not all(genre in valid_genres for genre in genre_list):
            booksLogger.error(f"Invalid genre specified | request #{g.requestNumber} ")
            return jsonify({"errorMessage": "Invalid genre specified"}), 400

    filtered_books = filterbooks(request)
    filtered_books = sorted(filtered_books, key=lambda book: book['title'].lower())
    booksLogger.info(f"Total Books found for requested filters is {len(filtered_books)} | request #{g.requestNumber}  ")
    return jsonify({"result": filtered_books}), 200


@app.route('/logs/level', methods=['GET'])
def GetLogLevel():
    # Retrieve the logger name from query parameters
    loggerName = request.args.get('logger-name')

    # Check if the logger name is valid
    if loggerName not in ['request-logger', 'books-logger']:
        return jsonify({"error": "Invalid logger name provided"}), 400

    # Get the logger based on the logger name
    logger = logging.getLogger(loggerName)

    # Get the log level of the logger in text format and uppercase
    logLevel = logging.getLevelName(logger.level).upper()

    # Return the log level
    return jsonify(logLevel), 200
@app.route('/logs/level', methods=['PUT'])
def ChangeLogLevel():
    # Retrieve the parameters from the query string
    loggerName = request.args.get('logger-name')
    newLevel = request.args.get('logger-level').upper()  # Convert to uppercase to match logging levels

    # Validate the logger name
    if loggerName not in ['request-logger', 'books-logger']:
        return jsonify({"error": "Invalid logger name provided"}), 400

    # Validate the log level
    validLevels = ['ERROR', 'INFO', 'DEBUG']
    if newLevel not in validLevels:
        return jsonify({"error": "Invalid log level provided"}), 400

    # Get the logger
    logger = logging.getLogger(loggerName)

    # Set the new log level
    logger.setLevel(getattr(logging, newLevel))

    return (newLevel), 200

def filterbooks(request):
    author = request.args.get('author')
    price_greater_than = request.args.get('price-bigger-than', type=int)
    price_less_than = request.args.get('price-less-than', type=int)
    year_greater_than = request.args.get('year-bigger-than', type=int)
    year_less_than = request.args.get('year-less-than', type=int)
    genres = request.args.get('genres')

    filtered_books = books

    if author:
        filtered_books = [book for book in filtered_books if book['author'].lower() == author.lower()]
    if price_greater_than is not None:
        filtered_books = [book for book in filtered_books if book['price'] >= price_greater_than]
    if price_less_than is not None:
        filtered_books = [book for book in filtered_books if book['price'] <= price_less_than]
    if year_greater_than is not None:
        filtered_books = [book for book in filtered_books if book['year'] >= year_greater_than]
    if year_less_than is not None:
        filtered_books = [book for book in filtered_books if book['year'] <= year_less_than]
    if genres:
        genre_list = genres.split(',')
        filtered_books = [book for book in filtered_books if any(genre in book['genres'] for genre in genre_list)]
    return filtered_books


def CheckBookName(bookName):
    lowKeyBookName = bookName.strip().lower()
    for book in books:
        if lowKeyBookName == book["title"].lower():
            print("found a match ")
            return False

    else:
        return True


def CheckBookPrice(bookPirce):
    print(bookPirce)
    if bookPirce <= 0:
        return False
    else:
        return True


def checkYear(bookyear):
    print("the book year is :", bookyear)
    if 1940 <= bookyear <= 2100:
        return True
    else:
        return False


if __name__ == '__main__':
    createLogFolder()
    setupRequestLogger()
    setupBooksLogger()
    app.run(host='0.0.0.0', port=8574)

