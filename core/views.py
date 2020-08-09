import stripe
import random
import string
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import get_object_or_404, redirect, render
from .models import Item, Order, OrderItem, Address, Payment, Coupon, Refund
from django.views.generic import ListView, DetailView, View
from django.utils import timezone
from .forms import CheckoutForm, CouponForm, RefundForm


stripe.api_key = settings.STRIPE_TEST_KEY


def create_ref_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


class HomeView(ListView):
    model = Item
    paginate_by = 10
    template_name = "core/home-page.html"


class OrderSummaryView(LoginRequiredMixin, View):

    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            context = {
                'object': order
            }
            return render(self.request, 'core/order_summary.html', context=context)
        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order")
            return redirect("/")


class ProductDetail(DetailView):
    template_name = 'core/product-page.html'
    model = Item


@login_required
def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(
        item=item,
        user=request.user,
        ordered=False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)

    if order_qs.exists():
        order = order_qs[0]

        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "Item quantity updated")
            return redirect("core:product", slug=slug)
        else:
            messages.info(request, "This item was added to your cart")
            order.items.add(order_item)
            return redirect("core:product", slug=slug)
    else:
        ordered_date = timezone.now()
        order = Order.objects.create(
            user=request.user, ordered_date=ordered_date)
        order.items.add(order_item)
        messages.info(request, "This item was added to your cart")
        return redirect("core:product", slug=slug)


@login_required
def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]

        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
            order.items.remove(order_item)
            messages.info(request, "This item was removed from your cart")
            return redirect("core:order-summary")
        else:
            # Add a message sayin the order doesn't contain the order item
            messages.info(request, "This item was not in your cart")
            return redirect("core:product", slug=slug)
    else:
        # add a message saying the user doesnt have an orderexist
        messages.info(request, "You do not have an active  order")
        return redirect("core:product", slug=slug)


def is_valid_form(values):
    valid = True
    for field in values:
        if field == '':
            valid = False
        return valid

class CheckoutView(View):
    def get(self, *args, **kwargs):
        # FORM

        try:
            form = CheckoutForm
            order = Order.objects.get(user=self.request.user, ordered=False)
            context = {
                "form": form,
                "order": order,
                "couponform": CouponForm(),
                "DISPLAY_COUPON_FORM": True
            }
            shipping_address_qs = Address.objects.filter(
                user=self.request.user,
                address_type="S",
                default=True)

            if shipping_address_qs.exists():
                context.update({
                    'default_shipping_address': shipping_address_qs[0],
                })

            billing_address_qs = Address.objects.filter(
                user=self.request.user,
                address_type="B",
                default=True)

            if billing_address_qs.exists():
                context.update({
                    'default_billing_address': billing_address_qs[0],
                })
            
            return render(self.request, 'core/checkout-page.html', context=context)
        except ObjectDoesNotExist as e:
            messages.info(self.request, "You do not have an active order")
            return redirect("core:checkout")

    # POST METHOD
    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST or None)
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if form.is_valid():
                use_default_shipping = form.cleaned_data.get('use_default_shipping')
                if use_default_shipping:
                    print("Using the default shipping address")
                    address_qs = Address.objects.filter(
                        user=self.request.user,
                        address_type="S",
                        default=True)
                    if address_qs.exists():
                        shipping_address = address_qs[0]
                        order.shipping_address = shipping_address
                        order.save()
                    else:
                        messages.info(self.request, "No default shipping address available")
                        return redirect("core:checkout")
                else:
                    print("User is entering a new shippipng address")
                    shipping_address1 = form.cleaned_data.get(
                        'shipping_address')
                    shipping_address2 = form.cleaned_data.get(
                        'shipping_address2')
                    shipping_country = form.cleaned_data.get(
                        'shipping_country')
                    shipping_zip = form.cleaned_data.get('shipping_zip')

                    if is_valid_form([shipping_address1,shipping_address2,shipping_country,shipping_zip]):
                        shipping_address = Address(
                            user=self.request.user,
                            street_address=shipping_address1,
                            appartment_address=shipping_address2,
                            country=shipping_country,
                            zip=shipping_zip,
                            address_type ='S'
                        )
                        shipping_address.save()
                        order.shipping_address = shipping_address
                        order.save()

                        set_default_shipping = form.cleaned_data.get(
                            'set_default_shipping')
                        if set_default_shipping:
                            shipping_address.default = True
                            shipping_address.save()
                    else:
                        messages.info(self.request, "Please fill in the required shipping address fields")
                
                # For Billing address
                use_default_billing = form.cleaned_data.get('use_default_billing')
                same_billing_address = form.cleaned_data.get('same_billing_address')
                if same_billing_address:
                    billing_address = shipping_address
                    billing_address.pk = None
                    billing_address.save()
                    billing_address.address_type="B"
                    billing_address.save()
                    order.billing_address = billing_address
                    order.save()

                elif use_default_billing:
                    print("Using the default billing address")
                    address_qs = Address.objects.filter(
                        user=self.request.user,
                        address_type="B",
                        default=True)
                    if address_qs.exists():
                        billing_address = address_qs[0]
                        order.billing_address = billing_address
                        order.save()
                    else:
                        messages.info(self.request, "No default billing address available")
                        return redirect("core:checkout")
                else:
                    print("User is entering a new billing address")
                    billing_address1 = form.cleaned_data.get(
                        'billing_address')
                    billing_address2 = form.cleaned_data.get(
                        'billing_address2')
                    billing_country = form.cleaned_data.get(
                        'billing_country')
                    billing_zip = form.cleaned_data.get('billing_zip')

                    if is_valid_form([billing_address1,billing_address2,billing_country,billing_zip]):
                        billing_address = Address(

                            user=self.request.user,
                            street_address=billing_address1,
                            appartment_address=billing_address2,
                            country=billing_country,
                            zip=billing_zip,
                            address_type ='B'
                        )
                        billing_address.save()
                        order.billing_address = billing_address
                        order.save()

                        set_default_billing = form.cleaned_data.get(
                            'set_default_billing')
                        if set_default_shipping:
                            billing_address.default = True
                            billing_address.save()
                    else:
                        messages.info(self.request, "Please fill in the required billing address fields")

                
                payment_option = form.cleaned_data.get('payment_option')
                if payment_option == 'S':
                    return redirect('core:payment', payment_option='stripe')
                elif payment_option == 'PP':
                    return redirect('core:payment', payment_option='paypal')
                else:
                    messages.warning(
                        self.request, "Invalid Payment option selected")
                    return redirect("core:checkout")
            messages.warning(self.request, "Failed Checkout")
            return redirect("core:order-summary")
        except ObjectDoesNotExist:
            messages.warning(self.request, "You do not have an active order")
            return redirect("/")


class PaymentView(View):
    def get(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        # to restrict someone from access this page without filling checkout form
        if order.billing_address:
            context = {
                'order': order,
                "DISPLAY_COUPON_FORM": False
            }
            return render(self.request, "core/payment.html", context=context)
        else:
            messages.warning(
                self.request, "You have not added a billing address")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        token = self.request.POST.get('stripeToken')
        amount = int(order.get_total() * 100)
        try:
            charge = stripe.Charge.create(
                amount=amount,
                currency="usd",
                source=token
            )

            # create payment
            payment = Payment()
            payment.stripe_charge_id = charge['id']
            payment.user = self.request.user
            payment.amount = order.get_total()
            payment.save()

            # assign payment to the order
            order_items = order.items.all()
            order_items.update(ordered=True)
            for item in order_items:
                item.save()
            order.ordered = True
            order.payment = payment
            order.ref_code = create_ref_code()
            order.save()

            messages.success(self.request, "Your request was successful")
            return redirect("/")

        except stripe.error.CardError as e:
            messages.warning(self.request, e.error.message)
            return redirect("/")

        except stripe.error.RateLimitError as e:
            # Too many requests made to the API too quickly
            messages.warning(self.request, "Rate limit error")
            return redirect("/")

        except stripe.error.InvalidRequestError as e:
            messages.warning(self.request, e.error.message)
            return redirect("/")

        except stripe.error.AuthenticationError as e:
            # Authentication with Stripe's API failed
            # (maybe you changed API keys recently)
            messages.warning(self.request, "Not authenticated")
            return redirect("/")

        except stripe.error.APIConnectionError as e:
            # Network communication with Stripe failed
            messages.warning(self.request, "Network error")
            return redirect("/")

        except stripe.error.StripeError as e:
            # Display a very generic error to the user, and maybe send
            # yourself an email
            messages.warning(
                self.request, "Something went wrong, you were not charged please try again")
            return redirect("/")

        except Exception as e:
            messages.warning(self.request, e)
            # self.request, "A serious error occured, we have been notified")
            return redirect("/")


@login_required
def remove_single_item_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]

        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(
                item=item,
                user=request.user,
                ordered=False
            )[0]
            if order_item.quantity > 1:
                order_item.quantity -= 1
                order_item.save()
            else:
                order.items.remove(order_item)
            messages.info(request, "Item quantity updated")
            return redirect("core:order-summary")


@login_required
def add_single_item_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(
        item=item,
        user=request.user,
        ordered=False
    )
    order_qs = Order.objects.filter(user=request.user, ordered=False)

    if order_qs.exists():
        order = order_qs[0]

        # check if the order item is in the order
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "Item quantity updated")
            return redirect("core:order-summary")


def add_Coupon(request, code):
    try:
        order = Order.objects.get(user=request.user, ordered=False)
        coupon = Coupon.objects.get(code=code)
    except ObjectDoesNotExist as ODNE:
        messages.info(request, "You do not have an active order")
        return redirect("core:checkout")


def getCoupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        return coupon
    except ObjectDoesNotExist as e:
        messages.info(request, "This coupon does not exist.")
        return redirect("core:checkout")


class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            try:
                code = form.cleaned_data.get('code')
                order = Order.objects.get(
                    user=self.request.user, ordered=False)
                order.coupon = getCoupon(self.request, code=code)
                order.save()
                messages.success(self.request, "Coupon successfully added")
                return redirect("core:checkout")
            except ObjectDoesNotExist as e:
                messages.info(self.request, "You do not have an active order")
                return redirect("core:checkout")
        # TODO: IMPLEMENT AN ERROR RAISE
        return messages.warning(self.request, "Somethings wrong with the coupon post methood")


class RequestRefundView(View):
    def get(self, *args, **kwargs):
        form = RefundForm()
        context = {
            'form':form
        }
        return render(self.request, "core/request_refund.html", context=context)

    def post(self, *args, **kwargs):
        form = RefundForm(self.request.POST)
        if form.is_valid():
            ref_code =  form.cleaned_data.get('ref_code')
            email =  form.cleaned_data.get('email')
            message = form.cleaned_data.get('message')
            #  edit the order
            try:
                order = Order.objects.get(ref_code=ref_code)
                order.refund_requested = True
                order.save()
                #Store the refund info
                refund = Refund()
                refund.order = order
                refund.reason = messages
                refund.email = email
                refund.save()
                messages.info(self.request, "Your request was recieved")
                return redirect("core:request-refund")

            except ObjectDoesNotExist:
                messages.info(self.request, "This order does not exist")
                return redirect("core:request-refund")
            
