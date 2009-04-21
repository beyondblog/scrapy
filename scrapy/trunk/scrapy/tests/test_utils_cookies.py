# -*- coding: latin-1 -*-
"""Tests for cookielib.py."""

import re, os, time
from unittest import TestCase

from test import test_support

from scrapy.http import Request, Response, Headers
from scrapy.utils.cookies import WrappedRequest, WrappedResponse, CookieJar, DefaultCookiePolicy


def interact_2965(cookiejar, url, *set_cookie_hdrs):
    return _interact(cookiejar, url, set_cookie_hdrs, "Set-Cookie2")

def interact_netscape(cookiejar, url, *set_cookie_hdrs):
    return _interact(cookiejar, url, set_cookie_hdrs, "Set-Cookie")

def _interact(cookiejar, url, set_cookie_hdrs, hdr_name):
    """Perform a single request / response cycle, returning Cookie: header."""
    req = Request(url)
    cookiejar.add_cookie_header(req)
    cookie_hdr = req.headers.get('Cookie', '')
    headers = {}
    if set_cookie_hdrs:
        headers[hdr_name] = set_cookie_hdrs
    res = Response(url, headers=headers)
    cookiejar.extract_cookies(res, req)
    return cookie_hdr


class CookieTests(TestCase):
    # XXX
    # Get rid of string comparisons where not actually testing str / repr.
    # .clear() etc.
    # IP addresses like 50 (single number, no dot) and domain-matching
    #  functions (and is_HDN)?  See draft RFC 2965 errata.
    # Strictness switches
    # is_third_party()
    # unverifiability / third-party blocking
    # Netscape cookies work the same as RFC 2965 with regard to port.
    # Set-Cookie with negative max age.
    # If turn RFC 2965 handling off, Set-Cookie2 cookies should not clobber
    #  Set-Cookie cookies.
    # Cookie2 should be sent if *any* cookies are not V1 (ie. V0 OR V2 etc.).
    # Cookies (V1 and V0) with no expiry date should be set to be discarded.
    # RFC 2965 Quoting:
    #  Should accept unquoted cookie-attribute values?  check errata draft.
    #   Which are required on the way in and out?
    #  Should always return quoted cookie-attribute values?
    # Proper testing of when RFC 2965 clobbers Netscape (waiting for errata).
    # Path-match on return (same for V0 and V1).
    # RFC 2965 acceptance and returning rules
    #  Set-Cookie2 without version attribute is rejected.

    # Netscape peculiarities list from Ronald Tschalar.
    # The first two still need tests, the rest are covered.
## - Quoting: only quotes around the expires value are recognized as such
##   (and yes, some folks quote the expires value); quotes around any other
##   value are treated as part of the value.
## - White space: white space around names and values is ignored
## - Default path: if no path parameter is given, the path defaults to the
##   path in the request-uri up to, but not including, the last '/'. Note
##   that this is entirely different from what the spec says.
## - Commas and other delimiters: Netscape just parses until the next ';'.
##   This means it will allow commas etc inside values (and yes, both
##   commas and equals are commonly appear in the cookie value). This also
##   means that if you fold multiple Set-Cookie header fields into one,
##   comma-separated list, it'll be a headache to parse (at least my head
##   starts hurting everytime I think of that code).
## - Expires: You'll get all sorts of date formats in the expires,
##   including emtpy expires attributes ("expires="). Be as flexible as you
##   can, and certainly don't expect the weekday to be there; if you can't
##   parse it, just ignore it and pretend it's a session cookie.
## - Domain-matching: Netscape uses the 2-dot rule for _all_ domains, not
##   just the 7 special TLD's listed in their spec. And folks rely on
##   that...

    def test_domain_return_ok(self):
        # test optimization: .domain_return_ok() should filter out most
        # domains in the CookieJar before we try to access them (because that
        # may require disk access -- in particular, with MSIECookieJar)
        # This is only a rough check for performance reasons, so it's not too
        # critical as long as it's sufficiently liberal.
        pol = DefaultCookiePolicy()
        for url, domain, ok in [
            ("http://foo.bar.com/", "blah.com", False),
            ("http://foo.bar.com/", "rhubarb.blah.com", False),
            ("http://foo.bar.com/", "rhubarb.foo.bar.com", False),
            ("http://foo.bar.com/", ".foo.bar.com", True),
            ("http://foo.bar.com/", "foo.bar.com", True),
            ("http://foo.bar.com/", ".bar.com", True),
            ("http://foo.bar.com/", "com", True),
            ("http://foo.com/", "rhubarb.foo.com", False),
            ("http://foo.com/", ".foo.com", True),
            ("http://foo.com/", "foo.com", True),
            ("http://foo.com/", "com", True),
            ("http://foo/", "rhubarb.foo", False),
            ("http://foo/", ".foo", True),
            ("http://foo/", "foo", True),
            ("http://foo/", "foo.local", True),
            ("http://foo/", ".local", True),
            ]:
            request = WrappedRequest(Request(url))
            r = pol.domain_return_ok(domain, request)
            if ok: self.assert_(r)
            else: self.assert_(not r)

    def test_rfc2109_handling(self):
        # RFC 2109 cookies are handled as RFC 2965 or Netscape cookies,
        # dependent on policy settings

        for rfc2109_as_netscape, rfc2965, version in [
            # default according to rfc2965 if not explicitly specified
            (None, False, 0),
            (None, True, 1),
            # explicit rfc2109_as_netscape
            (False, False, None),  # version None here means no cookie stored
            (False, True, 1),
            (True, False, 0),
            (True, True, 0),
            ]:
            policy = DefaultCookiePolicy(
                rfc2109_as_netscape=rfc2109_as_netscape,
                rfc2965=rfc2965)
            c = CookieJar(policy)
            interact_netscape(c, "http://www.example.com/", "ni=ni; Version=1")
            try:
                cookie = c._cookies["www.example.com"]["/"]["ni"]
            except KeyError:
                self.assert_(version is None)  # didn't expect a stored cookie
            else:
                self.assertEqual(cookie.version, version)
                # 2965 cookies are unaffected
                interact_2965(c, "http://www.example.com/",
                              "foo=bar; Version=1")
                if rfc2965:
                    cookie2965 = c._cookies["www.example.com"]["/"]["foo"]
                    self.assertEqual(cookie2965.version, 1)

    def test_ns_parser(self):
        from cookielib import DEFAULT_HTTP_PORT

        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/",
                          'spam=eggs; DoMain=.acme.com; port; blArgh="feep"')
        interact_netscape(c, "http://www.acme.com/", 'ni=ni; port=80,8080')
        interact_netscape(c, "http://www.acme.com:80/", 'nini=ni')
        interact_netscape(c, "http://www.acme.com:80/", 'foo=bar; expires=')
        interact_netscape(c, "http://www.acme.com:80/", 'spam=eggs; '
                          'expires="Foo Bar 25 33:22:11 3022"')

        cookie = c._cookies[".acme.com"]["/"]["spam"]
        self.assertEquals(cookie.domain, ".acme.com")
        self.assert_(cookie.domain_specified)
        self.assertEquals(cookie.port, DEFAULT_HTTP_PORT)
        self.assert_(not cookie.port_specified)
        # case is preserved
        self.assert_(cookie.has_nonstandard_attr("blArgh") and
                     not cookie.has_nonstandard_attr("blargh"))

        cookie = c._cookies["www.acme.com"]["/"]["ni"]
        self.assertEquals(cookie.domain, "www.acme.com")
        self.assert_(not cookie.domain_specified)
        self.assertEquals(cookie.port, "80,8080")
        self.assert_(cookie.port_specified)

        cookie = c._cookies["www.acme.com"]["/"]["nini"]
        self.assert_(cookie.port is None)
        self.assert_(not cookie.port_specified)

        # invalid expires should not cause cookie to be dropped
        foo = c._cookies["www.acme.com"]["/"]["foo"]
        spam = c._cookies["www.acme.com"]["/"]["foo"]
        self.assert_(foo.expires is None)
        self.assert_(spam.expires is None)

    def test_ns_parser_special_names(self):
        # names such as 'expires' are not special in first name=value pair
        # of Set-Cookie: header
        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/", 'expires=eggs')
        interact_netscape(c, "http://www.acme.com/", 'version=eggs; spam=eggs')

        cookies = c._cookies["www.acme.com"]["/"]
        self.assert_('expires' in cookies)
        self.assert_('version' in cookies)

    def test_expires(self):
        from cookielib import time2netscape

        # if expires is in future, keep cookie...
        c = CookieJar()
        future = time2netscape(time.time()+3600)
        interact_netscape(c, "http://www.acme.com/", 'spam="bar"; expires=%s' %
                          future)
        self.assertEquals(len(c), 1)
        now = time2netscape(time.time()-1)
        # ... and if in past or present, discard it
        interact_netscape(c, "http://www.acme.com/", 'foo="eggs"; expires=%s' %
                          now)
        h = interact_netscape(c, "http://www.acme.com/")
        self.assertEquals(len(c), 1)
        self.assert_('spam="bar"' in h and "foo" not in h)

        # max-age takes precedence over expires, and zero max-age is request to
        # delete both new cookie and any old matching cookie
        interact_netscape(c, "http://www.acme.com/", 'eggs="bar"; expires=%s' %
                          future)
        interact_netscape(c, "http://www.acme.com/", 'bar="bar"; expires=%s' %
                          future)
        self.assertEquals(len(c), 3)
        interact_netscape(c, "http://www.acme.com/", 'eggs="bar"; '
                          'expires=%s; max-age=0' % future)
        interact_netscape(c, "http://www.acme.com/", 'bar="bar"; '
                          'max-age=0; expires=%s' % future)
        h = interact_netscape(c, "http://www.acme.com/")
        self.assertEquals(len(c), 1)

        # test expiry at end of session for cookies with no expires attribute
        interact_netscape(c, "http://www.rhubarb.net/", 'whum="fizz"')
        self.assertEquals(len(c), 2)
        c.clear_session_cookies()
        self.assertEquals(len(c), 1)
        self.assert_('spam="bar"' in h)

        # XXX RFC 2965 expiry rules (some apply to V0 too)

    def test_default_path(self):
        # RFC 2965
        pol = DefaultCookiePolicy(rfc2965=True)

        c = CookieJar(pol)
        interact_2965(c, "http://www.acme.com/", 'spam="bar"; Version="1"')
        self.assert_("/" in c._cookies["www.acme.com"])

        c = CookieJar(pol)
        interact_2965(c, "http://www.acme.com/blah", 'eggs="bar"; Version="1"')
        self.assert_("/" in c._cookies["www.acme.com"])

        c = CookieJar(pol)
        interact_2965(c, "http://www.acme.com/blah/rhubarb",
                      'eggs="bar"; Version="1"')
        self.assert_("/blah/" in c._cookies["www.acme.com"])

        c = CookieJar(pol)
        interact_2965(c, "http://www.acme.com/blah/rhubarb/",
                      'eggs="bar"; Version="1"')
        self.assert_("/blah/rhubarb/" in c._cookies["www.acme.com"])

        # Netscape

        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/", 'spam="bar"')
        self.assert_("/" in c._cookies["www.acme.com"])

        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/blah", 'eggs="bar"')
        self.assert_("/" in c._cookies["www.acme.com"])

        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/blah/rhubarb", 'eggs="bar"')
        self.assert_("/blah" in c._cookies["www.acme.com"])

        c = CookieJar()
        interact_netscape(c, "http://www.acme.com/blah/rhubarb/", 'eggs="bar"')
        self.assert_("/blah/rhubarb" in c._cookies["www.acme.com"])

    def test_wrong_domain(self):
        # Cookies whose effective request-host name does not domain-match the
        # domain are rejected.

        # XXX far from complete
        c = CookieJar()
        interact_2965(c, "http://www.nasty.com/", 'foo=bar; domain=friendly.org; Version="1"')
        self.assertEquals(len(c), 0)

    def test_strict_domain(self):
        # Cookies whose domain is a country-code tld like .co.uk should
        # not be set if CookiePolicy.strict_domain is true.
        cp = DefaultCookiePolicy(strict_domain=True)
        cj = CookieJar(policy=cp)
        interact_netscape(cj, "http://example.co.uk/", 'no=problemo')
        interact_netscape(cj, "http://example.co.uk/",
                          'okey=dokey; Domain=.example.co.uk')
        self.assertEquals(len(cj), 2)
        for pseudo_tld in [".co.uk", ".org.za", ".tx.us", ".name.us"]:
            interact_netscape(cj, "http://example.%s/" % pseudo_tld,
                              'spam=eggs; Domain=.co.uk')
            self.assertEquals(len(cj), 2)

    def test_two_component_domain_ns(self):
        # Netscape: .www.bar.com, www.bar.com, .bar.com, bar.com, no domain
        # should all get accepted, as should .acme.com, acme.com and no domain
        # for 2-component domains like acme.com.
        c = CookieJar()

        # two-component V0 domain is OK
        interact_netscape(c, "http://foo.net/", 'ns=bar')
        self.assertEquals(len(c), 1)
        self.assertEquals(c._cookies["foo.net"]["/"]["ns"].value, "bar")
        self.assertEquals(interact_netscape(c, "http://foo.net/"), "ns=bar")
        # *will* be returned to any other domain (unlike RFC 2965)...
        self.assertEquals(interact_netscape(c, "http://www.foo.net/"),
                          "ns=bar")
        # ...unless requested otherwise
        pol = DefaultCookiePolicy(
            strict_ns_domain=DefaultCookiePolicy.DomainStrictNonDomain)
        c.set_policy(pol)
        self.assertEquals(interact_netscape(c, "http://www.foo.net/"), "")

        # unlike RFC 2965, even explicit two-component domain is OK,
        # because .foo.net matches foo.net
        interact_netscape(c, "http://foo.net/foo/",
                          'spam1=eggs; domain=foo.net')
        # even if starts with a dot -- in NS rules, .foo.net matches foo.net!
        interact_netscape(c, "http://foo.net/foo/bar/",
                          'spam2=eggs; domain=.foo.net')
        self.assertEquals(len(c), 3)
        self.assertEquals(c._cookies[".foo.net"]["/foo"]["spam1"].value,
                          "eggs")
        self.assertEquals(c._cookies[".foo.net"]["/foo/bar"]["spam2"].value,
                          "eggs")
        self.assertEquals(interact_netscape(c, "http://foo.net/foo/bar/"),
                          "spam2=eggs; spam1=eggs; ns=bar")

        # top-level domain is too general
        interact_netscape(c, "http://foo.net/", 'nini="ni"; domain=.net')
        self.assertEquals(len(c), 3)

##         # Netscape protocol doesn't allow non-special top level domains (such
##         # as co.uk) in the domain attribute unless there are at least three
##         # dots in it.
        # Oh yes it does!  Real implementations don't check this, and real
        # cookies (of course) rely on that behaviour.
        interact_netscape(c, "http://foo.co.uk", 'nasty=trick; domain=.co.uk')
##         self.assertEquals(len(c), 2)
        self.assertEquals(len(c), 4)

    def test_two_component_domain_rfc2965(self):
        pol = DefaultCookiePolicy(rfc2965=True)
        c = CookieJar(pol)

        # two-component V1 domain is OK
        interact_2965(c, "http://foo.net/", 'foo=bar; Version="1"')
        self.assertEquals(len(c), 1)
        self.assertEquals(c._cookies["foo.net"]["/"]["foo"].value, "bar")
        self.assertEquals(interact_2965(c, "http://foo.net/"),
                          "$Version=1; foo=bar")
        # won't be returned to any other domain (because domain was implied)
        self.assertEquals(interact_2965(c, "http://www.foo.net/"), "")

        # unless domain is given explicitly, because then it must be
        # rewritten to start with a dot: foo.net --> .foo.net, which does
        # not domain-match foo.net
        interact_2965(c, "http://foo.net/foo",
                      'spam=eggs; domain=foo.net; path=/foo; Version="1"')
        self.assertEquals(len(c), 1)
        self.assertEquals(interact_2965(c, "http://foo.net/foo"),
                          "$Version=1; foo=bar")

        # explicit foo.net from three-component domain www.foo.net *does* get
        # set, because .foo.net domain-matches .foo.net
        interact_2965(c, "http://www.foo.net/foo/",
                      'spam=eggs; domain=foo.net; Version="1"')
        self.assertEquals(c._cookies[".foo.net"]["/foo/"]["spam"].value,
                          "eggs")
        self.assertEquals(len(c), 2)
        self.assertEquals(interact_2965(c, "http://foo.net/foo/"),
                          "$Version=1; foo=bar")
        self.assertEquals(interact_2965(c, "http://www.foo.net/foo/"),
                          '$Version=1; spam=eggs; $Domain="foo.net"')

        # top-level domain is too general
        interact_2965(c, "http://foo.net/",
                      'ni="ni"; domain=".net"; Version="1"')
        self.assertEquals(len(c), 2)

        # RFC 2965 doesn't require blocking this
        interact_2965(c, "http://foo.co.uk/",
                      'nasty=trick; domain=.co.uk; Version="1"')
        self.assertEquals(len(c), 3)

    def test_domain_allow(self):
        c = CookieJar(policy=DefaultCookiePolicy(
            blocked_domains=["acme.com"],
            allowed_domains=["www.acme.com"]))

        req = Request("http://acme.com/")
        headers = {"Set-Cookie": "CUSTOMER=WILE_E_COYOTE; path=/"}
        res = Response("http://acme.com/", headers=headers)
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 0)

        req = Request("http://www.acme.com/")
        res = Response("http://www.acme.com/", headers=headers)
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 1)

        req = Request("http://www.coyote.com/")
        res = Response("http://www.coyote.com/", headers=headers)
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 1)

        # set a cookie with non-allowed domain...
        req = Request("http://www.coyote.com/")
        res = Response("http://www.coyote.com/", headers=headers)
        cookies = c.make_cookies(res, req)
        c.set_cookie(cookies[0])
        self.assertEquals(len(c), 2)
        # ... and check is doesn't get returned
        c.add_cookie_header(req)
        assert 'Cookie' not in req.headers

    def test_domain_block(self):
        pol = DefaultCookiePolicy(
            rfc2965=True, blocked_domains=[".acme.com"])

        c = CookieJar(policy=pol)
        headers = {'Set-Cookie': 'CUSTOMER=WILE_E_COYOTE; path=/'}

        req = Request("http://www.acme.com/")
        res = Response('http://www.acme.com/', headers=headers)
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 0)

        p = pol.set_blocked_domains(["acme.com"])
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 1)

        c.clear()
        req = Request("http://www.roadrunner.net/")
        res = Response("http://www.roadrunner.net/", headers=headers)
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 1)
        req = Request("http://www.roadrunner.net/")
        c.add_cookie_header(req)
        assert 'Cookie' in req.headers and 'Cookie2' in req.headers

        c.clear()
        pol.set_blocked_domains([".acme.com"])
        c.extract_cookies(res, req)
        self.assertEquals(len(c), 1)

        # set a cookie with blocked domain...
        req = Request("http://www.acme.com/")
        res = Response("http://www.acme.com/", headers=headers)
        cookies = c.make_cookies(res, req)
        c.set_cookie(cookies[0])
        self.assertEquals(len(c), 2)
        # ... and check is doesn't get returned
        c.add_cookie_header(req)
        assert 'Cookie' not in req.headers

    def test_secure(self):
        for ns in True, False:
            for whitespace in " ", "":
                c = CookieJar()
                if ns:
                    pol = DefaultCookiePolicy(rfc2965=False)
                    int = interact_netscape
                    vs = ""
                else:
                    pol = DefaultCookiePolicy(rfc2965=True)
                    int = interact_2965
                    vs = "; Version=1"
                c.set_policy(pol)
                url = "http://www.acme.com/"
                int(c, url, "foo1=bar%s%s" % (vs, whitespace))
                int(c, url, "foo2=bar%s; secure%s" %  (vs, whitespace))
                self.assert_(
                    not c._cookies["www.acme.com"]["/"]["foo1"].secure,
                    "non-secure cookie registered secure")
                self.assert_(
                    c._cookies["www.acme.com"]["/"]["foo2"].secure,
                    "secure cookie registered non-secure")

    def test_quote_cookie_value(self):
        c = CookieJar(policy=DefaultCookiePolicy(rfc2965=True))
        interact_2965(c, "http://www.acme.com/", r'foo=\b"a"r; Version=1')
        h = interact_2965(c, "http://www.acme.com/")
        self.assertEquals(h, r'$Version=1; foo=\\b\"a\"r')

    def test_missing_final_slash(self):
        # Missing slash from request URL's abs_path should be assumed present.
        url = "http://www.acme.com"
        c = CookieJar(DefaultCookiePolicy(rfc2965=True))
        interact_2965(c, url, "foo=bar; Version=1")
        req = Request(url)
        self.assertEquals(len(c), 1)
        c.add_cookie_header(req)
        self.assert_('Cookie' in req.headers)

    def test_domain_mirror(self):
        pol = DefaultCookiePolicy(rfc2965=True)

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, "spam=eggs; Version=1")
        h = interact_2965(c, url)
        self.assert_("Domain" not in h,
                     "absent domain returned with domain present")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, 'spam=eggs; Version=1; Domain=.bar.com')
        h = interact_2965(c, url)
        self.assert_('$Domain=".bar.com"' in h, "domain not returned")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        # note missing initial dot in Domain
        interact_2965(c, url, 'spam=eggs; Version=1; Domain=bar.com')
        h = interact_2965(c, url)
        self.assert_('$Domain="bar.com"' in h, "domain not returned")

    def test_path_mirror(self):
        pol = DefaultCookiePolicy(rfc2965=True)

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, "spam=eggs; Version=1")
        h = interact_2965(c, url)
        self.assert_("Path" not in h,
                     "absent path returned with path present")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, 'spam=eggs; Version=1; Path=/')
        h = interact_2965(c, url)
        self.assert_('$Path="/"' in h, "path not returned")

    def test_port_mirror(self):
        pol = DefaultCookiePolicy(rfc2965=True)

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, "spam=eggs; Version=1")
        h = interact_2965(c, url)
        self.assert_("Port" not in h,
                     "absent port returned with port present")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, "spam=eggs; Version=1; Port")
        h = interact_2965(c, url)
        self.assert_(re.search("\$Port([^=]|$)", h),
                     "port with no value not returned with no value")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, 'spam=eggs; Version=1; Port="80"')
        h = interact_2965(c, url)
        self.assert_('$Port="80"' in h,
                     "port with single value not returned with single value")

        c = CookieJar(pol)
        url = "http://foo.bar.com/"
        interact_2965(c, url, 'spam=eggs; Version=1; Port="80,8080"')
        h = interact_2965(c, url)
        self.assert_('$Port="80,8080"' in h,
                     "port with multiple values not returned with multiple "
                     "values")

    def test_no_return_comment(self):
        c = CookieJar(DefaultCookiePolicy(rfc2965=True))
        url = "http://foo.bar.com/"
        interact_2965(c, url, 'spam=eggs; Version=1; '
                      'Comment="does anybody read these?"; '
                      'CommentURL="http://foo.bar.net/comment.html"')
        h = interact_2965(c, url)
        self.assert_(
            "Comment" not in h,
            "Comment or CommentURL cookie-attributes returned to server")

    def test_Cookie_iterator(self):
        from cookielib import Cookie

        cs = CookieJar(DefaultCookiePolicy(rfc2965=True))
        # add some random cookies
        interact_2965(cs, "http://blah.spam.org/", 'foo=eggs; Version=1; '
                      'Comment="does anybody read these?"; '
                      'CommentURL="http://foo.bar.net/comment.html"')
        interact_netscape(cs, "http://www.acme.com/blah/", "spam=bar; secure")
        interact_2965(cs, "http://www.acme.com/blah/",
                      "foo=bar; secure; Version=1")
        interact_2965(cs, "http://www.acme.com/blah/",
                      "foo=bar; path=/; Version=1")
        interact_2965(cs, "http://www.sol.no",
                      r'bang=wallop; version=1; domain=".sol.no"; '
                      r'port="90,100, 80,8080"; '
                      r'max-age=100; Comment = "Just kidding! (\"|\\\\) "')

        versions = [1, 1, 1, 0, 1]
        names = ["bang", "foo", "foo", "spam", "foo"]
        domains = [".sol.no", "blah.spam.org", "www.acme.com",
                   "www.acme.com", "www.acme.com"]
        paths = ["/", "/", "/", "/blah", "/blah/"]

        for i in range(4):
            i = 0
            for c in cs:
                self.assert_(isinstance(c, Cookie))
                self.assertEquals(c.version, versions[i])
                self.assertEquals(c.name, names[i])
                self.assertEquals(c.domain, domains[i])
                self.assertEquals(c.path, paths[i])
                i = i + 1

    def test_bad_cookie_header(self):
        def cookiejar_from_cookie_headers(headers):
            c = CookieJar()
            req = Request("http://www.example.com/")
            r = Response("http://www.example.com/", headers=headers)
            c.extract_cookies(r, req)
            return c

        # none of these bad headers should cause an exception to be raised
        for headers in [
                {"Set-Cookie": ""},  # actually, nothing wrong with this
                {"Set-Cookie2": ""},  # ditto
            # missing domain value
                {"Set-Cookie2": "a=foo; path=/; Version=1; domain"},
            # bad max-age
                {"Set-Cookie": "b=foo; max-age=oops"},
                ]:
            c = cookiejar_from_cookie_headers(headers)
            # these bad cookies shouldn't be set
            self.assertEquals(len(c), 0)

        # cookie with invalid expires is treated as session cookie
        headers = {"Set-Cookie": "c=foo; expires=Foo Bar 12 33:22:11 2000"}
        c = cookiejar_from_cookie_headers(headers)
        cookie = c._cookies["www.example.com"]["/"]["c"]
        self.assert_(cookie.expires is None)


class LWPCookieTests(TestCase):
    # Tests taken from libwww-perl, with a few modifications and additions.

    def test_netscape_example_1(self):
        #-------------------------------------------------------------------
        # First we check that it works for the original example at
        # http://www.netscape.com/newsref/std/cookie_spec.html

        # Client requests a document, and receives in the response:
        #
        #       Set-Cookie: CUSTOMER=WILE_E_COYOTE; path=/; expires=Wednesday, 09-Nov-99 23:12:40 GMT
        #
        # When client requests a URL in path "/" on this server, it sends:
        #
        #       Cookie: CUSTOMER=WILE_E_COYOTE
        #
        # Client requests a document, and receives in the response:
        #
        #       Set-Cookie: PART_NUMBER=ROCKET_LAUNCHER_0001; path=/
        #
        # When client requests a URL in path "/" on this server, it sends:
        #
        #       Cookie: CUSTOMER=WILE_E_COYOTE; PART_NUMBER=ROCKET_LAUNCHER_0001
        #
        # Client receives:
        #
        #       Set-Cookie: SHIPPING=FEDEX; path=/fo
        #
        # When client requests a URL in path "/" on this server, it sends:
        #
        #       Cookie: CUSTOMER=WILE_E_COYOTE; PART_NUMBER=ROCKET_LAUNCHER_0001
        #
        # When client requests a URL in path "/foo" on this server, it sends:
        #
        #       Cookie: CUSTOMER=WILE_E_COYOTE; PART_NUMBER=ROCKET_LAUNCHER_0001; SHIPPING=FEDEX
        #
        # The last Cookie is buggy, because both specifications say that the
        # most specific cookie must be sent first.  SHIPPING=FEDEX is the
        # most specific and should thus be first.

        year_plus_one = time.localtime()[0] + 1

        c = CookieJar(DefaultCookiePolicy(rfc2965 = True))

        #req = Request("http://1.1.1.1/",
        #              headers={"Host": "www.acme.com:80"})
        req = Request("http://www.acme.com:80/", headers={"Host": "www.acme.com:80"})

        headers = Headers()
        headers['Set-Cookie'] = 'CUSTOMER=WILE_E_COYOTE; path=/ ; expires=Wednesday, 09-Nov-%d 23:12:40 GMT' % year_plus_one
        res = Response("http://www.acme.com/", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://www.acme.com/")
        c.add_cookie_header(req)

        self.assertEqual(req.headers.get("Cookie"), "CUSTOMER=WILE_E_COYOTE")
        self.assertEqual(req.headers.get("Cookie2"), '$Version="1"')

        headers.appendlist("Set-Cookie", "PART_NUMBER=ROCKET_LAUNCHER_0001; path=/")
        res = Response("http://www.acme.com/", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://www.acme.com/foo/bar")
        c.add_cookie_header(req)

        h = req.headers.get("Cookie")
        self.assert_("PART_NUMBER=ROCKET_LAUNCHER_0001" in h and
                     "CUSTOMER=WILE_E_COYOTE" in h)

        headers.appendlist('Set-Cookie', 'SHIPPING=FEDEX; path=/foo')
        res = Response("http://www.acme.com", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://www.acme.com/")
        c.add_cookie_header(req)

        h = req.headers.get("Cookie")
        self.assert_("PART_NUMBER=ROCKET_LAUNCHER_0001" in h and
                     "CUSTOMER=WILE_E_COYOTE" in h and
                     "SHIPPING=FEDEX" not in h)

        req = Request("http://www.acme.com/foo/")
        c.add_cookie_header(req)

        h = req.headers.get("Cookie")
        self.assert_(("PART_NUMBER=ROCKET_LAUNCHER_0001" in h and
                      "CUSTOMER=WILE_E_COYOTE" in h and
                      h.startswith("SHIPPING=FEDEX;")))

    def test_netscape_example_2(self):
        # Second Example transaction sequence:
        #
        # Assume all mappings from above have been cleared.
        #
        # Client receives:
        #
        #       Set-Cookie: PART_NUMBER=ROCKET_LAUNCHER_0001; path=/
        #
        # When client requests a URL in path "/" on this server, it sends:
        #
        #       Cookie: PART_NUMBER=ROCKET_LAUNCHER_0001
        #
        # Client receives:
        #
        #       Set-Cookie: PART_NUMBER=RIDING_ROCKET_0023; path=/ammo
        #
        # When client requests a URL in path "/ammo" on this server, it sends:
        #
        #       Cookie: PART_NUMBER=RIDING_ROCKET_0023; PART_NUMBER=ROCKET_LAUNCHER_0001
        #
        #       NOTE: There are two name/value pairs named "PART_NUMBER" due to
        #       the inheritance of the "/" mapping in addition to the "/ammo" mapping.

        c = CookieJar()
        headers = Headers({'Set-Cookie': 'PART_NUMBER=ROCKET_LAUNCHER_0001; path=/'})

        req = Request("http://www.acme.com/")
        res = Response("http://www.acme.com/", headers=headers)

        c.extract_cookies(res, req)

        req = Request("http://www.acme.com/")
        c.add_cookie_header(req)

        self.assertEquals(req.headers.get("Cookie"), "PART_NUMBER=ROCKET_LAUNCHER_0001")

        headers.appendlist("Set-Cookie", "PART_NUMBER=RIDING_ROCKET_0023; path=/ammo")
        res = Response("http://www.acme.com/", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://www.acme.com/ammo")
        c.add_cookie_header(req)

        self.assert_(re.search(r"PART_NUMBER=RIDING_ROCKET_0023;\s*"
                               "PART_NUMBER=ROCKET_LAUNCHER_0001",
                               req.headers.get("Cookie")))

    def test_ietf_example_1(self):
        #-------------------------------------------------------------------
        # Then we test with the examples from draft-ietf-http-state-man-mec-03.txt
        #
        # 5.  EXAMPLES

        c = CookieJar(DefaultCookiePolicy(rfc2965=True))

        #
        # 5.1  Example 1
        #
        # Most detail of request and response headers has been omitted.  Assume
        # the user agent has no stored cookies.
        #
        #   1.  User Agent -> Server
        #
        #       POST /acme/login HTTP/1.1
        #       [form data]
        #
        #       User identifies self via a form.
        #
        #   2.  Server -> User Agent
        #
        #       HTTP/1.1 200 OK
        #       Set-Cookie2: Customer="WILE_E_COYOTE"; Version="1"; Path="/acme"
        #
        #       Cookie reflects user's identity.

        cookie = interact_2965(
            c, 'http://www.acme.com/acme/login',
            'Customer="WILE_E_COYOTE"; Version="1"; Path="/acme"')
        self.assert_(not cookie)

        #
        #   3.  User Agent -> Server
        #
        #       POST /acme/pickitem HTTP/1.1
        #       Cookie: $Version="1"; Customer="WILE_E_COYOTE"; $Path="/acme"
        #       [form data]
        #
        #       User selects an item for ``shopping basket.''
        #
        #   4.  Server -> User Agent
        #
        #       HTTP/1.1 200 OK
        #       Set-Cookie2: Part_Number="Rocket_Launcher_0001"; Version="1";
        #               Path="/acme"
        #
        #       Shopping basket contains an item.

        cookie = interact_2965(c, 'http://www.acme.com/acme/pickitem',
                               'Part_Number="Rocket_Launcher_0001"; '
                               'Version="1"; Path="/acme"');
        self.assert_(re.search(
            r'^\$Version="?1"?; Customer="?WILE_E_COYOTE"?; \$Path="/acme"$',
            cookie))

        #
        #   5.  User Agent -> Server
        #
        #       POST /acme/shipping HTTP/1.1
        #       Cookie: $Version="1";
        #               Customer="WILE_E_COYOTE"; $Path="/acme";
        #               Part_Number="Rocket_Launcher_0001"; $Path="/acme"
        #       [form data]
        #
        #       User selects shipping method from form.
        #
        #   6.  Server -> User Agent
        #
        #       HTTP/1.1 200 OK
        #       Set-Cookie2: Shipping="FedEx"; Version="1"; Path="/acme"
        #
        #       New cookie reflects shipping method.

        cookie = interact_2965(c, "http://www.acme.com/acme/shipping",
                               'Shipping="FedEx"; Version="1"; Path="/acme"')

        self.assert_(re.search(r'^\$Version="?1"?;', cookie))
        self.assert_(re.search(r'Part_Number="?Rocket_Launcher_0001"?;'
                               '\s*\$Path="\/acme"', cookie))
        self.assert_(re.search(r'Customer="?WILE_E_COYOTE"?;\s*\$Path="\/acme"',
                               cookie))

        #
        #   7.  User Agent -> Server
        #
        #       POST /acme/process HTTP/1.1
        #       Cookie: $Version="1";
        #               Customer="WILE_E_COYOTE"; $Path="/acme";
        #               Part_Number="Rocket_Launcher_0001"; $Path="/acme";
        #               Shipping="FedEx"; $Path="/acme"
        #       [form data]
        #
        #       User chooses to process order.
        #
        #   8.  Server -> User Agent
        #
        #       HTTP/1.1 200 OK
        #
        #       Transaction is complete.

        cookie = interact_2965(c, "http://www.acme.com/acme/process")
        self.assert_(
            re.search(r'Shipping="?FedEx"?;\s*\$Path="\/acme"', cookie) and
            "WILE_E_COYOTE" in cookie)

        #
        # The user agent makes a series of requests on the origin server, after
        # each of which it receives a new cookie.  All the cookies have the same
        # Path attribute and (default) domain.  Because the request URLs all have
        # /acme as a prefix, and that matches the Path attribute, each request
        # contains all the cookies received so far.

    def test_ietf_example_2(self):
        # 5.2  Example 2
        #
        # This example illustrates the effect of the Path attribute.  All detail
        # of request and response headers has been omitted.  Assume the user agent
        # has no stored cookies.

        c = CookieJar(DefaultCookiePolicy(rfc2965=True))

        # Imagine the user agent has received, in response to earlier requests,
        # the response headers
        #
        # Set-Cookie2: Part_Number="Rocket_Launcher_0001"; Version="1";
        #         Path="/acme"
        #
        # and
        #
        # Set-Cookie2: Part_Number="Riding_Rocket_0023"; Version="1";
        #         Path="/acme/ammo"

        interact_2965(
            c, "http://www.acme.com/acme/ammo/specific",
            'Part_Number="Rocket_Launcher_0001"; Version="1"; Path="/acme"',
            'Part_Number="Riding_Rocket_0023"; Version="1"; Path="/acme/ammo"')

        # A subsequent request by the user agent to the (same) server for URLs of
        # the form /acme/ammo/...  would include the following request header:
        #
        # Cookie: $Version="1";
        #         Part_Number="Riding_Rocket_0023"; $Path="/acme/ammo";
        #         Part_Number="Rocket_Launcher_0001"; $Path="/acme"
        #
        # Note that the NAME=VALUE pair for the cookie with the more specific Path
        # attribute, /acme/ammo, comes before the one with the less specific Path
        # attribute, /acme.  Further note that the same cookie name appears more
        # than once.

        cookie = interact_2965(c, "http://www.acme.com/acme/ammo/...")
        self.assert_(
            re.search(r"Riding_Rocket_0023.*Rocket_Launcher_0001", cookie))

        # A subsequent request by the user agent to the (same) server for a URL of
        # the form /acme/parts/ would include the following request header:
        #
        # Cookie: $Version="1"; Part_Number="Rocket_Launcher_0001"; $Path="/acme"
        #
        # Here, the second cookie's Path attribute /acme/ammo is not a prefix of
        # the request URL, /acme/parts/, so the cookie does not get forwarded to
        # the server.

        cookie = interact_2965(c, "http://www.acme.com/acme/parts/")
        self.assert_("Rocket_Launcher_0001" in cookie and
                     "Riding_Rocket_0023" not in cookie)

    def test_url_encoding(self):
        # Try some URL encodings of the PATHs.
        # (the behaviour here has changed from libwww-perl)

        c = CookieJar(DefaultCookiePolicy(rfc2965=True))
        interact_2965(c, "http://www.acme.com/foo%2f%25/%3c%3c%0Anew%E5/%E5",
                      "foo  =   bar; version    =   1")

        cookie = interact_2965(
            c, "http://www.acme.com/foo%2f%25/<<%0anewå/æøå",
            'bar=baz; path="/foo/"; version=1');
        version_re = re.compile(r'^\$version=\"?1\"?', re.I)
        # FIXME: test disabled until fix
        #self.assert_("foo=bar" in cookie and version_re.search(cookie))

        cookie = interact_2965(
            c, "http://www.acme.com/foo/%25/<<%0anewå/æøå")
        self.assert_(not cookie)

        # unicode URL doesn't raise exception
        cookie = interact_2965(c, u"http://www.acme.com/\xfc")

    def test_netscape_misc(self):
        # Some additional Netscape cookies tests.
        c = CookieJar()
        headers = Headers()
        req = Request("http://foo.bar.acme.com/foo")

        # Netscape allows a host part that contains dots
        headers.appendlist("Set-Cookie", "Customer=WILE_E_COYOTE; domain=.acme.com")
        res = Response("http://www.acme.com/foo", headers=headers)
        c.extract_cookies(res, req)

        # and that the domain is the same as the host without adding a leading
        # dot to the domain.  Should not quote even if strange chars are used
        # in the cookie value.
        headers.appendlist("Set-Cookie", "PART_NUMBER=3,4; domain=foo.bar.acme.com")
        res = Response("http://www.acme.com/foo", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://foo.bar.acme.com/foo")
        c.add_cookie_header(req)
        self.assert_(
            "PART_NUMBER=3,4" in req.headers.get("Cookie") and
            "Customer=WILE_E_COYOTE" in req.headers.get("Cookie"))

    def test_intranet_domains_2965(self):
        # Test handling of local intranet hostnames without a dot.
        c = CookieJar(DefaultCookiePolicy(rfc2965=True))
        interact_2965(c, "http://example/",
                      "foo1=bar; PORT; Discard; Version=1;")
        cookie = interact_2965(c, "http://example/",
                               'foo2=bar; domain=".local"; Version=1')
        self.assert_("foo1=bar" in cookie)

        interact_2965(c, "http://example/", 'foo3=bar; Version=1')
        cookie = interact_2965(c, "http://example/")
        self.assert_("foo2=bar" in cookie and len(c) == 3)

    def test_intranet_domains_ns(self):
        c = CookieJar(DefaultCookiePolicy(rfc2965 = False))
        interact_netscape(c, "http://example/", "foo1=bar")
        cookie = interact_netscape(c, "http://example/",
                                   'foo2=bar; domain=.local')
        self.assertEquals(len(c), 2)
        self.assert_("foo1=bar" in cookie)

        cookie = interact_netscape(c, "http://example/")
        self.assert_("foo2=bar" in cookie)
        self.assertEquals(len(c), 2)

    def test_empty_path(self):
        # Test for empty path
        # Broken web-server ORION/1.3.38 returns to the client response like
        #
        #       Set-Cookie: JSESSIONID=ABCDERANDOM123; Path=
        #
        # ie. with Path set to nothing.
        # In this case, extract_cookies() must set cookie to / (root)
        c = CookieJar(DefaultCookiePolicy(rfc2965 = True))
        headers = Headers({'Set-Cookie': 'JSESSIONID=ABCDERANDOM123; Path='})

        req = Request("http://www.ants.com/")
        res = Response("http://www.ants.com/", headers=headers)
        c.extract_cookies(res, req)

        req = Request("http://www.ants.com/")
        c.add_cookie_header(req)

        self.assertEquals(req.headers.get("Cookie"),
                          "JSESSIONID=ABCDERANDOM123")
        self.assertEquals(req.headers.get("Cookie2"), '$Version="1"')

        # missing path in the request URI
        req = Request("http://www.ants.com:8080")
        c.add_cookie_header(req)

        self.assertEquals(req.headers.get("Cookie"),
                          "JSESSIONID=ABCDERANDOM123")
        self.assertEquals(req.headers.get("Cookie2"), '$Version="1"')

    def test_session_cookies(self):
        year_plus_one = time.localtime()[0] + 1

        # Check session cookies are deleted properly by
        # CookieJar.clear_session_cookies method

        req = Request('http://www.perlmeister.com/scripts')
        headers = Headers()
        headers.appendlist("Set-Cookie", "s1=session;Path=/scripts")
        headers.appendlist("Set-Cookie", "p1=perm; Domain=.perlmeister.com;Path=/;expires=Fri, 02-Feb-%d 23:24:20 GMT" % year_plus_one)
        headers.appendlist("Set-Cookie", "p2=perm;Path=/;expires=Fri, 02-Feb-%d 23:24:20 GMT" % year_plus_one)
        headers.appendlist("Set-Cookie", "s2=session;Path=/scripts;" "Domain=.perlmeister.com")
        headers.appendlist('Set-Cookie2', 's3=session;Version=1;Discard;Path="/"')
        res = Response('http://www.perlmeister.com/scripts', headers=headers)

        c = CookieJar()
        c.extract_cookies(res, req)
        # How many session/permanent cookies do we have?
        counter = {"session_after": 0,
                   "perm_after": 0,
                   "session_before": 0,
                   "perm_before": 0}
        for cookie in c:
            key = "%s_before" % cookie.value
            counter[key] = counter[key] + 1
        c.clear_session_cookies()
        # How many now?
        for cookie in c:
            key = "%s_after" % cookie.value
            counter[key] = counter[key] + 1

        self.assert_(not (
            # a permanent cookie got lost accidently
            counter["perm_after"] != counter["perm_before"] or
            # a session cookie hasn't been cleared
            counter["session_after"] != 0 or
            # we didn't have session cookies in the first place
            counter["session_before"] == 0))



class WrapperRequestResponse(TestCase):

    def FakeRequest(self, url, data='', headers={}):
        tail = '?' + urllib.quote(data) if data else ''
        return WrappedRequest(Request('%s%s' % (url, tail), headers=headers))

    def test_request_path(self):
        from cookielib import request_path
        # with parameters
        req = self.FakeRequest("http://www.example.com/rheum/rhaponicum;"
                      "foo=bar;sing=song?apples=pears&spam=eggs#ni")
        self.assertEquals(request_path(req), "/rheum/rhaponicum;"
                     "foo=bar;sing=song?apples=pears&spam=eggs#ni")
        # without parameters
        req = self.FakeRequest("http://www.example.com/rheum/rhaponicum?"
                      "apples=pears&spam=eggs#ni")
        self.assertEquals(request_path(req), "/rheum/rhaponicum?"
                     "apples=pears&spam=eggs#ni")
        # missing final slash
        req = self.FakeRequest("http://www.example.com")
        self.assertEquals(request_path(req), "/")

    def test_request_port(self):
        from cookielib import request_port, DEFAULT_HTTP_PORT
        req = self.FakeRequest("http://www.acme.com:1234/", headers={"Host": "www.acme.com:4321"})
        self.assertEquals(request_port(req), "1234")
        req = self.FakeRequest("http://www.acme.com/", headers={"Host": "www.acme.com:4321"})
        self.assertEquals(request_port(req), DEFAULT_HTTP_PORT)

    def test_request_host(self):
        from cookielib import request_host
        # this request is illegal (RFC2616, 14.2.3)
        req = self.FakeRequest("http://1.1.1.1/", headers={"Host": "www.acme.com:80"})
        # libwww-perl wants this response, but that seems wrong (RFC 2616,
        # section 5.2, point 1., and RFC 2965 section 1, paragraph 3)
        #self.assertEquals(request_host(req), "www.acme.com")
        self.assertEquals(request_host(req), "1.1.1.1")
        req = self.FakeRequest("http://www.acme.com/", headers={"Host": "irrelevant.com"})
        self.assertEquals(request_host(req), "www.acme.com")
        # not actually sure this one is valid Request object, so maybe should
        # remove test for no host in url in request_host function?
        req = self.FakeRequest("/resource.html", headers={"Host": "www.acme.com"})
        self.assertEquals(request_host(req), "www.acme.com")
        # port shouldn't be in request-host
        req = self.FakeRequest("http://www.acme.com:2345/resource.html", headers={"Host": "www.acme.com:5432"})
        self.assertEquals(request_host(req), "www.acme.com")
