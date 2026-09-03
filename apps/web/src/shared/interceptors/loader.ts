import { Injectable } from '@angular/core';
import { HttpRequest, HttpHandler, HttpEvent, HttpInterceptor, HttpErrorResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, throwError } from 'rxjs';
import { catchError, finalize, tap } from 'rxjs/operators';
import { Loader } from '../services/loader';
import { GlobalLoader } from '../services/global-loader'; 

@Injectable()
export class LoadingInterceptor implements HttpInterceptor {
    private chatRequests = 0;
    private otherRequests = 0;

    constructor(
        private chatLoader: Loader,      
        private globalLoader: GlobalLoader, 
        private router: Router
    ) {}

    intercept(request: HttpRequest<unknown>, next: HttpHandler): Observable<HttpEvent<unknown>> {

        const isChatReq = request.url.includes('api/chat');

        if (isChatReq) {
            // Loader per le chiamate chat
            this.chatRequests++;
            this.chatLoader.setLoading(true);

            return next.handle(request).pipe(
                tap(() => {}),
                catchError((error: HttpErrorResponse) => {
                    if (error.status === 401) {
                        this.router.navigate(['/']);
                    }
                    return throwError(() => error);
                }),
                finalize(() => {
                    this.chatRequests--;
                    if (this.chatRequests === 0) {
                        this.chatLoader.setLoading(false);
                    }
                })
            );

        } else {
            // Loader per tutte le altre chiamate
            this.otherRequests++;
            this.globalLoader.setLoading(true);

            return next.handle(request).pipe(
                tap(() => {}),
                catchError((error: HttpErrorResponse) => {
                    if (error.status === 401) {
                        this.router.navigate(['/']);
                    }
                    return throwError(() => error);
                }),
                finalize(() => {
                    this.otherRequests--;
                    if (this.otherRequests === 0) {
                        this.globalLoader.setLoading(false);
                    }
                })
            );
        }
    }
}
