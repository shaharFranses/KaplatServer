from flask import Flask, request, jsonify, g

from pymongo import MongoClient
import os
import logging
from logging.handlers import RotatingFileHandler
import time
import psycopg2
from psycopg2 import sql

app = Flask(__name__)

ALLOWED_GENRES = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
books = []
requestCounter = 0
numberofbooks=0


POSTGRES_URI = "postgresql://postgres:docker@localhost:5432/books"
MONGO_URI = "mongodb://localhost:27017/"


# Postgres configuration
#app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:docker@postgres:5432/books'




# Mongo configuration
mongo_client = MongoClient('mongodb://mongo:27017/')
mongo_db = mongo_client['books']
mongo_collection = mongo_db['books']


def get_new_Id():
    postgres_path = "postgresql://postgres:docker@localhost:5432/books"
    Mongo_path = "mongodb://localhost:27017/"

    # Connect to Postgres

    try:
        postgres_conn = psycopg2.connect(postgres_path)
        postgres_cursor = postgres_conn.cursor()
        postgres_cursor.execute("SELECT MAX(rawid) FROM books;")
        Current_amount_of_books = postgres_cursor.fetchone()[0] or 0
    except Exception as e:
        print(f"Error querying Postgres: {e}")
        Current_amount_of_books = 0
    finally:
        postgres_cursor.close()

    return Current_amount_of_books+1

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

def add_book_to_databases(new_book):
    """
    Adds a new book to both Postgres and MongoDB databases.

    Args:
        new_book (dict): The book details to be added.
    """
    booksLogger = logging.getLogger('books-logger')
    new_id = get_new_Id()

    # Add to Postgres
    try:
        postgres_conn = psycopg2.connect(POSTGRES_URI)
        postgres_cursor = postgres_conn.cursor()
        postgres_cursor.execute(
            """
            INSERT INTO books (rawid, title, author, year, price, genres)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (new_id, new_book['title'], new_book['author'], new_book['year'], new_book['price'], ','.join(new_book['genres']))
        )
        postgres_conn.commit()
    except Exception as e:
        booksLogger.error(f"Error adding book to Postgres: {e}")
    finally:
        if 'postgres_cursor' in locals():
            postgres_cursor.close()
        if 'postgres_conn' in locals():
            postgres_conn.close()

    # Add to MongoDB
    try:
        mongo_client = MongoClient(MONGO_URI)
        mongo_db = mongo_client['books']
        mongo_collection = mongo_db['books']
        mongo_collection.insert_one({
            "rawid": new_id,
            "title": new_book['title'],
            "author": new_book['author'],
            "year": new_book['year'],
            "price": new_book['price'],
            "genres": new_book['genres']
        })
    except Exception as e:
        booksLogger.error(f"Error adding book to MongoDB: {e}")

def fetch_book_by_Id_with_postgres(rawid):
    try:
        postgres_conn = psycopg2.connect(POSTGRES_URI)
        postgres_cursor = postgres_conn.cursor()
        query = "SELECT * FROM books WHERE rawid = %s;"
        postgres_cursor.execute(query, (rawid,))
        record = postgres_cursor.fetchone()
        postgres_cursor.close()
        if record:
            return record  # Adjust based on your schema
        else:
            return None
    except Exception as e:
        print(f"Error fetching from PostgreSQL: {e}")
        return None

def fetch_book_by_Id_with_mongo(rawid):

    try:
        mongo_client = MongoClient(MONGO_URI)
        mongo_db = mongo_client['books']
        mongo_collection = mongo_db['books']
        record = mongo_collection.find_one({"rawid": rawid})
        if record:
            record["_id"] = str(record["_id"])  # Convert ObjectId to string
        return record
    except Exception as e:
        print(f"Error fetching from MongoDB: {e}")
        return None
    query = {}
# Apply filters
    if "author" in filters:
        query["author"] = {"$regex": f"^{filters['author']}$", "$options": "i"}  # Case-insensitive match
    if "price-bigger-than" in filters:
        query["price"] =            {"$gte": filters["price-bigger-than"]}
    if "price-less-than" in filters:
        query["price"] = {"$lte": filters["price-less-than"], **query.get("price", {})}
    if "year-bigger-than" in filters:
        query["year"] = {"$gte": filters["year-bigger-than"]}
    if "year-less-than" in filters:
        query["year"] = {"$lte": filters["year-less-than"], **query.get("year", {})}
    if "genres" in filters:
        query["genres"] = {"$in": filters["genres"]}

    count = mongo_collection.count_documents(query)

def fetch_total_of_books_with_posgres(filters):
    postgres_conn = psycopg2.connect(POSTGRES_URI)

    query = "SELECT COUNT(*) FROM books WHERE TRUE"
    params = []

    # Apply filters
    if "author" in filters:
        query += " AND LOWER(author) = %s"
        params.append(filters["author"].lower())
    if "price-bigger-than" in filters:
        query += " AND price >= %s"
        params.append(filters["price-bigger-than"])
    if "price-less-than" in filters:
        query += " AND price <= %s"
        params.append(filters["price-less-than"])
    if "year-bigger-than" in filters:
        query += " AND year >= %s"
        params.append(filters["year-bigger-than"])
    if "year-less-than" in filters:
        query += " AND year <= %s"
        params.append(filters["year-less-than"])
    if "genres" in filters:
        genre_conditions = []
        for genre in filters["genres"]:
            genre_conditions.append("genres ILIKE %s")
            params.append(f"%{genre}%")  # Add wildcard for partial matching
        query += f" AND ({' OR '.join(genre_conditions)})"


    print(query)
    postgres_conn = psycopg2.connect(POSTGRES_URI)

    cursor = postgres_conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchone()
    cursor.close()

    return result[0]
def fetch_total_of_books_with_mongo(filters):
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client['books']
    mongo_collection = mongo_db['books']
    query = {}

    # Apply filters
    if "author" in filters:
        query["author"] = {"$regex": f"^{filters['author']}$", "$options": "i"}  # Case-insensitive match
    if "price-bigger-than" in filters:
        query["price"] = {"$gte": filters["price-bigger-than"]}
    if "price-less-than" in filters:
        query["price"] = {"$lte": filters["price-less-than"], **query.get("price", {})}
    if "year-bigger-than" in filters:
        query["year"] = {"$gte": filters["year-bigger-than"]}
    if "year-less-than" in filters:
        query["year"] = {"$lte": filters["year-less-than"], **query.get("year", {})}
    if "genres" in filters:
        query["genres"] = {"$in": filters["genres"]}

    count = mongo_collection.count_documents(query)
    return count


def fetch_total_of_books_with_details_with_Postgres(filters):

    query = "SELECT * FROM books WHERE TRUE"
    params = []

    # Apply filters
    if "author" in filters:
        query += " AND LOWER(author) = %s"
        params.append(filters["author"].lower())
    if "price-bigger-than" in filters:
        query += " AND price >= %s"
        params.append(filters["price-bigger-than"])
    if "price-less-than" in filters:
        query += " AND price <= %s"
        params.append(filters["price-less-than"])
    if "year-bigger-than" in filters:
        query += " AND year >= %s"
        params.append(filters["year-bigger-than"])
    if "year-less-than" in filters:
        query += " AND year <= %s"
        params.append(filters["year-less-than"])
    if "genres" in filters:
        genre_conditions = []
        for genre in filters["genres"]:
            genre_conditions.append("genres ILIKE %s")
            params.append(f"%{genre}%")  # Add wildcard for partial matching
        query += f" AND ({' OR '.join(genre_conditions)})"


    print(query)
    postgres_conn = psycopg2.connect(POSTGRES_URI)

    cursor = postgres_conn.cursor()
    cursor.execute(query, params)
    result = cursor.fetchall()
    cursor.close()

    return result

def fetch_total_of_books_with_details_with_Mongo(filters):
    mongo_client = MongoClient(MONGO_URI)
    mongo_db = mongo_client['books']
    mongo_collection = mongo_db['books']
    query = {}

    # Apply filters for other fields
    if "author" in filters:
        query["author"] = {"$regex": f"^{filters['author']}$", "$options": "i"}  # Case-insensitive match
    if "price-bigger-than" in filters:
        query["price"] = {"$gte": filters["price-bigger-than"]}
    if "price-less-than" in filters:
        query["price"] = {"$lte": filters["price-less-than"], **query.get("price", {})}
    if "year-bigger-than" in filters:
        query["year"] = {"$gte": filters["year-bigger-than"]}
    if "year-less-than" in filters:
        query["year"] = {"$lte": filters["year-less-than"], **query.get("year", {})}

    # Handle genres with $in
    if "genres" in filters:
        query["genres"] = {"$in": filters["genres"]}

    try:
        # Fetch matching documents from MongoDB
        results = list(mongo_collection.find(query))
        for result in results:
            result["_id"] = str(result["_id"])  # Convert ObjectId to string for JSON compatibility
        return results
    except Exception as e:
        print(f"Error executing MongoDB query: {e}")
        return None



def update_book_price(id,newPirce):
 try:
    mongo_client = MongoClient("mongodb://localhost:27017/")
    mongo_db = mongo_client["your_database_name"]
    mongo_collection = mongo_db["books"]
    postgres_connection = psycopg2.connect(POSTGRES_URI)
    postgres_cursor = postgres_connection.cursor()
    postgres_query = "UPDATE books SET price = %s WHERE rawid = %s"
    postgres_cursor.execute(postgres_query, (newPirce, id))
    postgres_connection.commit()

    # Update in MongoDB
    mongo_query = {"rawid": id}
    new_values = {"$set": {"price": newPirce}}
    mongo_result = mongo_collection.update_one(mongo_query, new_values)

    # Check if the updates were successful
    postgres_rows_updated = postgres_cursor.rowcount
    mongo_rows_updated = mongo_result.modified_count

    postgres_cursor.close()

    if postgres_rows_updated > 0 and mongo_rows_updated > 0:
        return f"Book with ID {id} successfully updated in both databases!"
    elif postgres_rows_updated > 0:
        return f"Book with ID {id} updated in PostgreSQL but not in MongoDB."
    elif mongo_rows_updated > 0:
        return f"Book with ID {id} updated in MongoDB but not in PostgreSQL."
    else:
        return f"Book with ID {id} not found in either database."
 except Exception as e:
    print(f"Error updating book price: {e}")
    return "An error occurred while updating the book price."


def delete_books_from_both_dbs(id):
    mongo_client = MongoClient("mongodb://localhost:27017/")
    mongo_db = mongo_client["your_database_name"]
    mongo_collection = mongo_db["books"]
    postgres_connection = psycopg2.connect(POSTGRES_URI)
    postgres_cursor = postgres_connection.cursor()
    postgres_query = "DELETE FROM books WHERE rawid = %s"
    postgres_cursor.execute(postgres_query, (id,))
    postgres_connection.commit()
    postgres_rows_deleted = postgres_cursor.rowcount
    postgres_cursor.close()
    mongo_query = {"rawid": int(id) }
    mongo_result = mongo_collection.delete_one(mongo_query)
    mongo_rows_deleted = mongo_result.deleted_count



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
        new_book={
                "id": books.__len__() + 1,
                "title": data['title'].strip(),
                "author": data['author'].strip(),
                "year": int(data['year']),
                "price": int(data['price']),
                "genres": [genre.strip() for genre in data['genres']]
            }

        books.append(new_book)
        ##adding to the DB'S :
        add_book_to_databases(new_book)
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
    db_type = request.args.get('persistenceMethod')


    if genres:
        genre_list = genres.split(',')
        valid_genres = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
        if not all(genre in valid_genres for genre in genre_list):
            booksLogger.error(f"Invalid genre specified | request #{g.requestNumber} ")
            return jsonify({"errorMessage": "Invalid genre specified"}), 400

    filters = {}
    author = request.args.get('author')
    price_bigger_than = request.args.get('price-bigger-than', type=float)
    price_less_than = request.args.get('price-less-than', type=float)
    year_bigger_than = request.args.get('year-bigger-than', type=int)
    year_less_than = request.args.get('year-less-than', type=int)
    genres = request.args.get('genres')

    if author:
        filters["author"] = author
    if price_bigger_than is not None:
        filters["price-bigger-than"] = price_bigger_than
    if price_less_than is not None:
        filters["price-less-than"] = price_less_than
    if year_bigger_than is not None:
        filters["year-bigger-than"] = year_bigger_than
    if year_less_than is not None:
        filters["year-less-than"] = year_less_than
    if genres:
        genres_list = genres.split(",")  # Split the comma-separated string into a list
        if not all(genre in ALLOWED_GENRES for genre in genres_list):  # Validate genres
            return jsonify({"error": "Invalid genres. Must be one of the allowed genres in capital case"}), 400
        filters["genres"] = genres_list  # Add the parsed list to filters


    if db_type =='MONGO':
        results=fetch_total_of_books_with_mongo(filters)
    else:
        results = fetch_total_of_books_with_posgres(filters)



    booksLogger.info(
        f"Total Books found for requested filters is {str(results)} | request #{g.requestNumber} ")
    return jsonify({"result": str(results)}), 200


@app.route('/book', methods=['Get'])
def getBookById():
    booksLogger = logging.getLogger('books-logger')
    rawid = request.args.get('id', type=int)
    db_type = request.args.get('persistenceMethod')


    if db_type=='MONGO':
        book=fetch_book_by_Id_with_mongo(rawid)
    else:
        book = fetch_book_by_Id_with_postgres(rawid)

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

    book = fetch_book_by_Id_with_postgres(id)
    if book is None:
        Errormessage = f"Error: no such Book with id {id}"
        errorCode = 404
        validRequst = False

    if validRequst == False:
        booksLogger.error(f"{Errormessage} | request #{g.requestNumber}")
        return jsonify({"errorMessage": Errormessage}), errorCode

    else:
        oldPrice=book[3]
        update_book_price(id,newPrice)

        return jsonify({"result": oldPrice}), 200


@app.route('/book', methods=['DELETE'])
def removeBook():
    booksLogger = logging.getLogger('books-logger')
    BookToRemove = None
    id = int(request.args.get('id'))

    BookToRemove=fetch_book_by_Id_with_postgres((id))
    delete_books_from_both_dbs(id)

    if BookToRemove:
        filters = {}
        num_of_books=fetch_total_of_books_with_details_with_Postgres(filters)
        return jsonify({"result": num_of_books}), 200


    else:
        booksLogger.error(f"Error: no such Book with id {id} | request #{g.requestNumber} ")
        return jsonify({"errorMessage": f"Error: no such Book with id {id}"}), 404


@app.route('/books', methods=['GET'])
def getBooks():
    booksLogger = logging.getLogger('books-logger')
    genres = request.args.get('genres')
    db_type = request.args.get('persistenceMethod')


    if genres:
        genre_list = genres.split(',')
        valid_genres = ["SCI_FI", "NOVEL", "HISTORY", "MANGA", "ROMANCE", "PROFESSIONAL"]
        if not all(genre in valid_genres for genre in genre_list):
            booksLogger.error(f"Invalid genre specified | request #{g.requestNumber} ")
            return jsonify({"errorMessage": "Invalid genre specified"}), 400


    filters = {}
    author = request.args.get('author')
    price_bigger_than = request.args.get('price-bigger-than', type=float)
    price_less_than = request.args.get('price-less-than', type=float)
    year_bigger_than = request.args.get('year-bigger-than', type=int)
    year_less_than = request.args.get('year-less-than', type=int)
    genres = request.args.get('genres')

    if author:
        filters["author"] = author
    if price_bigger_than is not None:
        filters["price-bigger-than"] = price_bigger_than
    if price_less_than is not None:
        filters["price-less-than"] = price_less_than
    if year_bigger_than is not None:
        filters["year-bigger-than"] = year_bigger_than
    if year_less_than is not None:
        filters["year-less-than"] = year_less_than
    if genres:
        genres_list = genres.split(",")  # Split the comma-separated string into a list
        if not all(genre in ALLOWED_GENRES for genre in genres_list):  # Validate genres
            return jsonify({"error": "Invalid genres. Must be one of the allowed genres in capital case"}), 400
        filters["genres"] = genres_list  # Add the parsed list to filters

    if db_type == 'MONGO':
        books = fetch_total_of_books_with_details_with_Mongo(filters)
    else:
        books = fetch_total_of_books_with_details_with_Postgres(filters)



    filtered_books = filterbooks(request)
    filtered_books = sorted(filtered_books, key=lambda book: book['title'].lower())
    booksLogger.info(f"Total Books found for requested filters is {len(filtered_books)} | request #{g.requestNumber}  ")
    return jsonify({"result": books}), 200


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

