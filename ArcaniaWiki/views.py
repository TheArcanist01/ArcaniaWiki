from django.http import HttpResponse

def index(request):
    return HttpResponse("<h1>Arcania Wiki</h1><p>A database for the Borderlands 2 Arcania mod</p>")

