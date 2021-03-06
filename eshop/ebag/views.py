from django.shortcuts import render, redirect
from django.views.generic import ListView
from django.views.generic.base import TemplateView
from django.http import JsonResponse
from django.conf import settings
from .models import Category, Product
from .forms import CheckoutForm
from functools import wraps
import json
# Create your views here.


class GeneralContextMixin:
    """
    Retrives from the DB the most common content
    shared on many views. Contains only static methods
    so serves just as a namespace for this group of methods.
    """

    @staticmethod
    def common_data(request, ctx=None):
        """
        Returns common data used in many views:
        1) Categories tree
        2) Cart
        3) items_in_cart
        If ctx is passed as a dict, adds its data to the
        returned result as well.

        :param request: passed from Django
        :type request:  WSGIRequest
        :param request: Optional dict which to be included in the
                        function returned result.
        :type request: dict / NoneType by default
        """

        if ctx is None:
            ctx = {}
        ctx['categories'] = Category.objects.all()
        ctx["items_in_cart"] = 0
        if "cart" in request.session:
            ctx["cart"] = [
                item for key, item in request.session["cart"].items()
            ]
            cart_total = sum([
                int(item["quantity"]) * float(item["product_data"]["price"])
                for item in ctx["cart"]
            ])
            ctx["cart_total"] = cart_total
        else:
            ctx["cart"] = []
        ctx["items_in_cart"] = len(ctx["cart"])
        return ctx

    @staticmethod
    def validate_referrer(valid_referrers):
        """
        Decorator.
        Redirects to the home page if the
        request referrer is not found in
        the list of valid referrers.
        Use cases:
        1) The user should not go to the checkout
        if not coming from the cart page.
        2) The "thank you" page must be visited
        only after coming from the checkout process

        :param valid_referrers: the list of valid referrers
        :type valid_referrers: list

        """
        def outer_wrapper(function):
            @wraps(function)
            def inner_wrapper(request, *args, **kwargs):
                referrer = str(request.META.get('HTTP_REFERER'))
                if all(r not in referrer for r in valid_referrers):
                    return redirect('home_view')
                return function(request, *args, **kwargs)
            return inner_wrapper
        return outer_wrapper

    @staticmethod
    def verify_cart_not_empty(function):
        """
        Decorator.
        If he cart is empty and the user tries to go
        to the cart or checkput page, redirects the user to the homepage.

        :param function: The decorated view
        :type function: function

        """
        @wraps(function)
        def inner_dec(request, *args, **kwargs):
            if "cart" not in request.session:
                return redirect('home_view')
            return function(request, *args, **kwargs)
        return inner_dec


class CategoryView(ListView):
    """
    Loads the products from a specific category
    """
    template_name = 'category.html'
    model = Category

    def get_context_data(self, **kwargs):
        """
        Prepares for passing to the template a context, containing:
        1) The current category data
        2) The products belonging to the category
        3) The estimated displayed quantity of each product based
        on the session history
        """

        ctx = super(__class__, self).get_context_data(**kwargs)
        ctx['category'] = Category.objects.get(id=self.kwargs["cat_id"])
        ctx['products'] = Product.objects.filter(
            category_id=self.kwargs["cat_id"]
        ).values()
        for product in ctx['products']:
            product_id = str(product["id"])
            session = self.request.session
            if ("cart" not in session or product_id not in session["cart"]):
                product["quantity"] = 1
            else:
                product["quantity"] = session["cart"][product_id]["quantity"]
        return GeneralContextMixin.common_data(self.request, ctx)


def home_view(request):
    return render(
        request,
        "home.html",
        GeneralContextMixin.common_data(request)
    )


@GeneralContextMixin.verify_cart_not_empty
def cart_view(request):
    return render(
        request,
        "cart.html",
        GeneralContextMixin.common_data(request)
    )


@GeneralContextMixin.validate_referrer(['/checkout/'])
def thank_you_view(request):
    """
    Displayed after successful checkout.
    """
    return render(
        request,
        "thank-you.html",
        GeneralContextMixin.common_data(request)
    )


@GeneralContextMixin.verify_cart_not_empty
@GeneralContextMixin.validate_referrer(['/cart/', '/checkout/'])
def checkout_view(request):
    form = CheckoutForm()
    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            del request.session["cart"]
            request.session.save()
            return redirect("thank_you_view")
    ctx = {
        "form": form
    }
    return render(
        request,
        "checkout.html",
        GeneralContextMixin.common_data(request, ctx)
    )


class AJAXSessionCart(TemplateView):
    template_name = None

    def set_init_vars(self):
        """
        Assigns to the class the main
        varibales, later used in the JSON response
        """
        self.success = 1
        self.items_in_cart = 0
        self.err_msg = ""
        if "cart" not in self.request.session:
            self.request.session["cart"] = {}
        self.cart = self.request.session["cart"]

    def set_cart(self):
        """
        Deletes the session cart if it's empty.
        Assigns to the object cart property
        an empty dict if the cart is empty
        or the session cart if it's not empty.
        """
        if self.items_in_cart < 1:
            del self.request.session["cart"]
            self.request.session.save()
        try:
            self.cart = self.request.session["cart"]
        except KeyError:
            self.cart = {}

    def post(self, request):
        """
        Sets the default returned values for the JSON output.
        Validates the input data.
        Processes each item by saving it in the session cart
        and calls the return function.
        """
        self.set_init_vars()
        for item in json.loads(request.POST["items"]):
            product_id = item["product_id"]
            quantity = item["quantity"]
            if not self.is_valid_ajax_input((product_id, quantity)):
                return self.return_error(settings.ERR_MSG_INVALID_PARAMS)
            int_quantity = int(quantity)
            if int_quantity > 0:
                product = Product.objects.filter(id=product_id)
                if not product:
                    return self.return_error(settings.ERR_MSG_NO_PRODUCT)
                else:
                    self.update_cart_with_product(
                        product_id,
                        quantity,
                        product
                    )
            else:
                self.delete_product_from_cart(product_id)
        self.request.session.save()
        self.items_in_cart = len(self.request.session["cart"])
        self.set_cart()
        return self.return_json()

    def return_error(self, error):
        """
        Eventually returns JsonResponse
        with a certain AJAX error.

        :param error: The error message
        :type error: Str
        """

        self.success = 0
        self.err_msg = error
        return self.return_json()

    def delete_product_from_cart(self, product_id):
        """
        Removes a product from cart.

        :param var: product_id
        :type var: str
        """
        try:
            del self.request.session["cart"][product_id]
        except KeyError:
            pass

    def update_cart_with_product(self, product_id, quantity, product):
        """
        Adds/updates a product in cart.

        :param product_id: The product id
        :type product_id: str
        :param quantity: Quantity
        :type quantity: str
        :param product: The product filtered queryset
        :type product: QuerySet
        """
        product_data = {
                k: str(v) for k, v in
                product.values()[0].items()
            }
        self.request.session["cart"].update(
            {product_id: {
                "quantity": quantity,
                "product_data": product_data
                }
             }
        )

    def return_json(self):
        """
        Returns the JSON output to the front-end.
        """
        data = {
            'success': self.success,
            'err_msg': self.err_msg,
            'items_in_cart': self.items_in_cart,
            'cart': self.cart
        }
        return JsonResponse(data)

    def is_valid_ajax_input(self, fields):
        """
        Returns True if all the fields
        are string representaions of integers,
        e.g. "4", "6"

        :param fields: A tuple with the fields
        :type fields: tuple
        """
        if any(isinstance(f, str) is not True for f in fields):
            return False
        if any(f.isdigit() is not True for f in fields):
            return False
        return True
