import psycopg2


# localhost
def get_connection():
    # localhost
    return psycopg2.connect(
        host="localhost",
        dbname="db_ar",
        user="postgres",
        password="password",
        port="5433"
    )


# Server
# def get_connection():
#     # localhost
#     return psycopg2.connect(
#         host="192.168.1.13",
#         dbname="db_ar",
#         user="postgres",
#         password="mbpi",
#         port="5432"
#     )
