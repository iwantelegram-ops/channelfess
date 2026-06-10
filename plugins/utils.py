# Utility functions bisa ditambahkan di sini
def paginate(data, page_size=15):
    for i in range(0, len(data), page_size):
        yield data[i:i+page_size]
